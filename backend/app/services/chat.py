import json
import logging
from collections.abc import AsyncGenerator
from functools import lru_cache

from openai import APIConnectionError, APIError, AsyncOpenAI

from app.adapters.retrievers import DenseRetriever
from app.config import settings
from app.services.token_usage import record_usage

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "你是企業內部知識助理，只能根據下方提供的「檢索內容」回答使用者問題。"
    "若檢索內容不足以回答問題，必須明確回答「目前查無相關資料，無法回答」，"
    "禁止臆測、編造或使用檢索內容以外的知識作答。"
    "回答中每個引用自檢索內容的陳述，句尾都要附上該段檢索內容提供的「[來源：...]」標籤，"
    "標籤文字須與檢索內容中的標籤完全一致，不可自行改寫或省略。"
)


@lru_cache
def _get_client() -> AsyncOpenAI:
    return AsyncOpenAI(api_key=settings.openai_api_key)


def _citation_label(chunk: dict) -> str:
    """組出 `[來源：...]` 標籤內文，同時供 prompt context 與 citations SSE 事件使用，
    確保前端能用同一段文字比對出訊息裡的 citation 標籤對應哪筆結構化資料。
    """
    if chunk.get("sheet_name"):
        return f"{chunk['file_name']}，工作表：{chunk['sheet_name']} {chunk.get('cell_range') or ''}".strip()
    return f"{chunk['file_name']}，第 {chunk.get('page_number')} 頁"


def _format_context(chunks: list[dict]) -> str:
    if not chunks:
        return "（本次查詢沒有檢索到任何相關文件內容）"

    blocks = [f"[來源：{_citation_label(chunk)}]\n{chunk['content']}" for chunk in chunks]
    return "\n\n".join(blocks)


def _build_citations(chunks: list[dict]) -> list[dict]:
    """去重後的 citation 結構化列表（見 roadmap Day 7 Citation 跳轉 API）：
    `label` 與 prompt context 裡的 `[來源：...]` 標籤文字完全一致，前端靠這個欄位比對訊息中
    出現的標籤，再用 document_id + page_number/sheet_name+cell_range 打 Citation 跳轉 API。
    """
    seen: set[str] = set()
    citations = []
    for chunk in chunks:
        label = _citation_label(chunk)
        if label in seen:
            continue
        seen.add(label)
        citations.append(
            {
                "label": label,
                "document_id": chunk["document_id"],
                "file_name": chunk["file_name"],
                "page_number": chunk.get("page_number"),
                "sheet_name": chunk.get("sheet_name"),
                "cell_range": chunk.get("cell_range"),
            }
        )
    return citations


def _build_messages(query: str, chunks: list[dict]) -> list[dict]:
    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": f"檢索內容：\n{_format_context(chunks)}\n\n使用者問題：{query}"},
    ]


def _sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def stream_chat_response(
    query: str,
    tenant_id: str,
    role: str,
    user_id: str,
    departments: list[str] | None = None,
    top_k: int | None = None,
) -> AsyncGenerator[str, None]:
    """`POST /api/query` 用：檢索 → 組 prompt → OpenAI stream=True 逐段轉成 SSE 事件（見 roadmap Day 6）。

    SSE 僅限本端點使用（見 CLAUDE.md Guardrail #3），事件格式：
    - event: citations → data: {"citations": [...]}（見 roadmap Day 7，檢索到內容時才送出，早於 message）
    - event: message → data: {"delta": "<文字片段>"}
    - event: error   → data: {"message": "<錯誤訊息>"}（發生後即結束串流）
    - event: done    → data: {}（正常結束時的最後一個事件）
    """
    try:
        chunks = await DenseRetriever().retrieve(
            query=query, tenant_id=tenant_id, top_k=top_k or settings.retrieval_top_k, departments=departments, role=role
        )
    except Exception as exc:
        logger.exception("Chat 檢索失敗")
        yield _sse_event("error", {"message": f"檢索失敗：{exc}"})
        return

    if chunks:
        yield _sse_event("citations", {"citations": _build_citations(chunks)})

    usage = None
    try:
        stream = await _get_client().chat.completions.create(
            model=settings.chat_model,
            messages=_build_messages(query, chunks),
            stream=True,
            stream_options={"include_usage": True},
        )
        async for chunk in stream:
            if chunk.usage is not None:
                usage = chunk.usage
            if not chunk.choices:
                # stream_options.include_usage 會在 [DONE] 前多送一個 choices 為空陣列、
                # 只帶 usage 的 chunk（見 OpenAI Python SDK ChatCompletionChunk 定義）。
                continue
            delta = chunk.choices[0].delta.content
            if delta:
                yield _sse_event("message", {"delta": delta})
    except (APIError, APIConnectionError) as exc:
        logger.exception("Chat 串流中斷")
        yield _sse_event("error", {"message": f"AI 回應中斷：{exc}"})
        return

    if usage is not None:
        record_usage(
            tenant_id=tenant_id,
            user_id=user_id,
            feature="chat",
            model=settings.chat_model,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
        )

    yield _sse_event("done", {})
