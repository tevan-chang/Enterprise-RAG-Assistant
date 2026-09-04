import json
import logging
from collections.abc import AsyncGenerator
from functools import lru_cache

from openai import APIConnectionError, APIError, AsyncOpenAI

from app.adapters.retrievers import DenseRetriever
from app.config import settings

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "你是企業內部知識助理，只能根據下方提供的「檢索內容」回答使用者問題。"
    "若檢索內容不足以回答問題，必須明確回答「目前查無相關資料，無法回答」，"
    "禁止臆測、編造或使用檢索內容以外的知識作答。"
)


@lru_cache
def _get_client() -> AsyncOpenAI:
    return AsyncOpenAI(api_key=settings.openai_api_key)


def _format_context(chunks: list[dict]) -> str:
    if not chunks:
        return "（本次查詢沒有檢索到任何相關文件內容）"

    blocks = []
    for chunk in chunks:
        if chunk.get("sheet_name"):
            source = f"{chunk['file_name']}，工作表：{chunk['sheet_name']} {chunk.get('cell_range') or ''}".strip()
        else:
            source = f"{chunk['file_name']}，第 {chunk.get('page_number')} 頁"
        blocks.append(f"[來源：{source}]\n{chunk['content']}")
    return "\n\n".join(blocks)


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
    departments: list[str] | None = None,
    top_k: int | None = None,
) -> AsyncGenerator[str, None]:
    """`POST /api/query` 用：檢索 → 組 prompt → OpenAI stream=True 逐段轉成 SSE 事件（見 roadmap Day 6）。

    SSE 僅限本端點使用（見 CLAUDE.md Guardrail #3），事件格式：
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

    try:
        stream = await _get_client().chat.completions.create(
            model=settings.chat_model,
            messages=_build_messages(query, chunks),
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield _sse_event("message", {"delta": delta})
    except (APIError, APIConnectionError) as exc:
        logger.exception("Chat 串流中斷")
        yield _sse_event("error", {"message": f"AI 回應中斷：{exc}"})
        return

    yield _sse_event("done", {})
