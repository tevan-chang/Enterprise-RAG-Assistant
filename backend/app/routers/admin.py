from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException

from app.adapters.notifications import GmailAPINotificationAdapter, NotificationError
from app.config import settings
from app.dependencies.auth import require_role
from app.schemas.admin import SyncKnowledgeBaseResponse, TestNotificationResponse
from app.services.sync import run_incremental_sync

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])

_ADMIN_ROLES = {"admin"}


def require_sync_api_key(x_api_key: str = Header()) -> None:
    """供外部 GitHub Actions Cron 打 sync-knowledge-base 用的 API Key 驗證（見 spec §5）。

    不用 JWT——這支端點沒有登入使用者 session，呼叫方是外部排程服務，比照
    dependencies/auth.py 的 get_current_user「驗證失敗就 raise HTTPException(401, ...)」風格。
    """
    if not settings.sync_api_key or x_api_key != settings.sync_api_key:
        raise HTTPException(status_code=401, detail="無效的 API Key")


@router.post(
    "/sync-knowledge-base",
    response_model=SyncKnowledgeBaseResponse,
    dependencies=[Depends(require_sync_api_key)],
)
async def sync_knowledge_base(background_tasks: BackgroundTasks):
    """外部 Cron（GitHub Actions）帶 API Key 觸發的增量同步（見 spec §5 / roadmap Day 9-10）。

    實際同步邏輯經 BackgroundTasks 非同步派發，不阻塞這支端點的回應（見 Guardrail #1）。
    """
    background_tasks.add_task(run_incremental_sync)
    return SyncKnowledgeBaseResponse(status="sync_started")


@router.post(
    "/test-notification",
    response_model=TestNotificationResponse,
    dependencies=[Depends(require_role(_ADMIN_ROLES))],
)
async def test_notification():
    """Dev/Admin 健檢端點：測試 Gmail API 憑證連線與 MIME 郵件發送狀態（見 spec §5）。

    刻意不透過 services/notifications.send_notification()——那個包裝會吞掉所有例外，
    但這支端點本身就是健檢用途，必須把失敗真實回報給呼叫端，所以直接用 Adapter，
    讓 NotificationError 轉成 502。
    """
    try:
        await GmailAPINotificationAdapter().send(
            settings.admin_notification_email,
            "[測試] Gmail API 通知健檢",
            "<p>這是一封測試郵件，確認 Gmail API 憑證與連線正常。</p>",
        )
    except NotificationError as exc:
        raise HTTPException(status_code=502, detail=f"Gmail 通知寄送失敗: {exc}") from exc
    return TestNotificationResponse(status="ok")
