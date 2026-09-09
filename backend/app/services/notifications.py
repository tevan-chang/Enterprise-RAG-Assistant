import logging

import sentry_sdk

from app.adapters.notifications import BaseNotificationService, GmailAPINotificationAdapter
from app.config import settings

logger = logging.getLogger(__name__)

DOCUMENT_PROCESSED = "DOCUMENT_PROCESSED"
FLAG_FOR_REVIEW = "FLAG_FOR_REVIEW"
RAG_SYNC_COMPLETED = "RAG_SYNC_COMPLETED"


def _build_content(scenario: str, context: dict) -> tuple[str, str]:
    """三種通知情境各自的 subject/html 樣板（見 spec §2.1）：純函式、不打任何外部服務，
    方便單獨測試 payload 結構。收件人目前一律固定為 settings.admin_notification_email
    （見使用者指示），包含 DOCUMENT_PROCESSED——規格書原意是通知上傳者本人，MVP 階段
    刻意先不建「依上傳者查 email」的查詢鏈路，之後才做動態收件人解析。
    """
    if scenario == DOCUMENT_PROCESSED:
        file_name = context.get("file_name", "")
        document_id = context.get("document_id", "")
        subject = f"文件處理完成通知：{file_name}"
        html = (
            f"<p>文件「{file_name}」已完成解析與索引，狀態為 completed。</p>"
            f"<p>document_id: {document_id}</p>"
        )
        return subject, html

    if scenario == FLAG_FOR_REVIEW:
        document_id = context.get("document_id", "")
        subject = "⚠️ 已鎖定文件內容異動，待審查"
        html = (
            f"<p>文件 {document_id} 的內容已變更，但分類狀態原為 manually_verified"
            f"（已人工鎖定），系統未自動解鎖，請登入後台確認是否需要重新整理分類。</p>"
        )
        return subject, html

    if scenario == RAG_SYNC_COMPLETED:
        zombie_marked_failed = context.get("zombie_marked_failed", 0)
        subject = "知識庫增量同步完成報告"
        html = (
            f"<p>本次增量同步已完成。</p>"
            f"<p>清理孤兒處理任務（zombie task）並標記為 failed 的文件數：{zombie_marked_failed}</p>"
        )
        return subject, html

    raise ValueError(f"未知的通知情境: {scenario}")


async def send_notification(
    scenario: str,
    context: dict,
    adapter: BaseNotificationService | None = None,
) -> None:
    """三個掛載點（DOCUMENT_PROCESSED/FLAG_FOR_REVIEW/RAG_SYNC_COMPLETED）共用的統一包裝，
    比照 services/token_usage.py 的 record_usage()：內部一律 catch 所有例外並 log + Sentry，
    寄送失敗不可影響呼叫端主流程，呼叫端不需要各自包 try/except。
    """
    try:
        subject, html = _build_content(scenario, context)
        await (adapter or GmailAPINotificationAdapter()).send(
            settings.admin_notification_email, subject, html
        )
    except Exception as exc:
        logger.error("Gmail 通知寄送失敗: scenario=%s err=%s", scenario, exc)
        sentry_sdk.capture_exception(exc)
