import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration

from app.config import settings


def init_sentry() -> None:
    """Sentry 接入（見 spec §2.5 / roadmap Day 9）。

    StarletteIntegration + FastApiIntegration 接手一般請求生命週期內的未捕捉例外
    （對應 CLAUDE.md 的「FastAPI exception middleware」要求）。BackgroundTasks 是在
    response 回傳「之後」才執行，不在這兩個 integration 能攔截的範圍內，因此
    document_pipeline / zombie_cleanup / classification / report 各自的失敗路徑
    改在對應的 except 分支手動呼叫 `sentry_sdk.capture_exception`/`capture_message`。

    未設定 SENTRY_DSN（例如本地開發沒申請帳號）時直接跳過；sentry_sdk 在未 init
    的情況下呼叫 capture_* 一律是安全的 no-op，不需要額外的 if 判斷散落各處。
    """
    if not settings.sentry_dsn:
        return

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        integrations=[StarletteIntegration(), FastApiIntegration()],
        traces_sample_rate=1.0,
        send_default_pii=False,
    )
