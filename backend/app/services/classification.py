import hashlib
import json
import logging
from functools import lru_cache

import sentry_sdk
from fastapi import BackgroundTasks
from openai import AsyncOpenAI

from app.config import settings
from app.repositories.documents_repository import DocumentsRepository
from app.services.notifications import FLAG_FOR_REVIEW, send_notification
from app.services.token_usage import record_usage

logger = logging.getLogger(__name__)

_CLASSIFY_SYSTEM_PROMPT = (
    "你是企業文件分類助理。根據提供的檔名與文件內容片段，判斷這份文件屬於哪些業務分類"
    "（例如：財務報表、人資政策、法務合約、行銷企劃、技術文件等），輸出 1 到 3 個最相關的中文分類標籤。"
    "只輸出 JSON array（例如 [\"財務報表\", \"季度報告\"]），不要 markdown code fence，不要任何前後說明文字。"
)


@lru_cache
def _get_client() -> AsyncOpenAI:
    return AsyncOpenAI(api_key=settings.openai_api_key)


async def auto_classify(
    document_id: str,
    tenant_id: str,
    user_id: str,
    file_name: str,
    chunk_texts: list[str],
    documents_repo: DocumentsRepository | None = None,
) -> None:
    """文件解析/embedding 成功完成後觸發（見 services/document_pipeline._embed_and_store_chunks
    尾段），把 classification_status 從 pending_auto 推進為 auto_labeled（見 spec §4.2）。

    只餵檔名 + 前 1~2 個 chunk 給 LLM（不是全文），比照 Day 8 Schema-First 的 Token 節制精神。
    分類失敗（LLM 呼叫或 JSON 解析失敗）不可讓文件變成 failed——解析與 embedding 都已成功，
    文件本身可用，這裡一律 log + sentry_sdk.capture_exception，classification_status 留在
    pending_auto（比照 zombie_cleanup.py / flag_for_review 既有的手動 capture 慣例）。
    """
    repo = documents_repo or DocumentsRepository()
    content_preview = "\n\n".join(chunk_texts[:2])
    user_prompt = f"檔名：{file_name}\n\n內容片段：\n{content_preview}"

    try:
        response = await _get_client().chat.completions.create(
            model=settings.chat_model,
            messages=[
                {"role": "system", "content": _CLASSIFY_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        )
        raw = response.choices[0].message.content or "[]"
        categories = json.loads(raw)
        if not isinstance(categories, list) or not all(isinstance(item, str) for item in categories):
            raise ValueError(f"分類結果非字串陣列: {raw!r}")
    except Exception as exc:
        logger.error("自動分類失敗: doc=%s err=%s", document_id, exc)
        sentry_sdk.capture_exception(exc)
        return

    record_usage(
        tenant_id=tenant_id,
        user_id=user_id,
        feature="classification",
        model=settings.chat_model,
        prompt_tokens=response.usage.prompt_tokens,
        completion_tokens=response.usage.completion_tokens,
    )
    repo.apply_auto_classification(document_id, categories, tenant_id)


def flag_for_review(document_id: str, background_tasks: BackgroundTasks | None = None) -> None:
    """已鎖定文件內容變更時觸發，警報通知 Admin（見 spec §4.3 / §2.1 情境 2）。

    log + Sentry 記錄一律保留（同 app/services/zombie_cleanup.py 的作法，方便維運追蹤），
    另外經 BackgroundTasks 非同步派發 Gmail 通知，不阻塞呼叫端（reupload API）的回應時間。
    `background_tasks` 為 None 時（例如既有測試直接呼叫本函式）僅記 log，不寄信，
    避免呼叫端一定要提供 BackgroundTasks 才能用這個函式。
    """
    logger.warning("文件內容變更但分類已鎖定，標記待審查（flag_for_review）: doc_id=%s", document_id)
    sentry_sdk.capture_message(f"flag_for_review 觸發：文件內容變更但分類已鎖定 doc_id={document_id}", level="warning")
    if background_tasks is not None:
        background_tasks.add_task(send_notification, FLAG_FOR_REVIEW, {"document_id": document_id})


def on_file_reupload(
    document_id: str,
    new_content: bytes,
    documents_repo: DocumentsRepository | None = None,
    background_tasks: BackgroundTasks | None = None,
) -> bool:
    """見 spec §4.3：hash 變更且原狀態為 manually_verified → flag_for_review，
    不自動解鎖（classification_status 維持 manually_verified，交由 Admin 判斷）。

    回傳是否觸發了 flag_for_review。
    """
    repo = documents_repo or DocumentsRepository()
    doc = repo.get(document_id)
    if doc is None:
        raise ValueError(f"document not found: {document_id}")

    new_hash = hashlib.sha256(new_content).hexdigest()
    if doc["file_content_hash"] != new_hash and doc["classification_status"] == "manually_verified":
        flag_for_review(document_id, background_tasks=background_tasks)
        return True
    return False
