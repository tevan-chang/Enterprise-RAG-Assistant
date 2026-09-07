import hashlib
import logging

import sentry_sdk

from app.repositories.documents_repository import DocumentsRepository

logger = logging.getLogger(__name__)


def flag_for_review(document_id: str) -> None:
    """已鎖定文件內容變更時觸發，警報通知 Admin（見 spec §4.3 / §2.1 情境 2）。

    TODO(Day 9-10): 改接 GmailAPINotificationAdapter 的 FLAG_FOR_REVIEW 情境，
    目前先用 log + Sentry 佔位（同 app/services/zombie_cleanup.py 的作法）。
    """
    logger.warning("文件內容變更但分類已鎖定，標記待審查（flag_for_review）: doc_id=%s", document_id)
    sentry_sdk.capture_message(f"flag_for_review 觸發：文件內容變更但分類已鎖定 doc_id={document_id}", level="warning")


def on_file_reupload(
    document_id: str,
    new_content: bytes,
    documents_repo: DocumentsRepository | None = None,
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
        flag_for_review(document_id)
        return True
    return False
