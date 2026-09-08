import logging

import sentry_sdk

from app.repositories.token_usage_repository import TokenUsageRepository

logger = logging.getLogger(__name__)


def record_usage(
    tenant_id: str,
    user_id: str,
    feature: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    repo: TokenUsageRepository | None = None,
) -> None:
    """記錄一次 LLM/Embedding 呼叫的 token 用量（見 spec §10 Demo 版計費）。

    四個記錄點（chat/report/embedding/classification）共用這個包裝：記錄失敗一律
    log + Sentry，不可影響呼叫端的主流程回應，因此這裡是唯一 catch 例外的地方，
    呼叫端不需要各自包 try/except。
    """
    try:
        (repo or TokenUsageRepository()).record(
            tenant_id=tenant_id,
            user_id=user_id,
            feature=feature,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
    except Exception as exc:
        logger.error("token usage 記錄失敗: feature=%s tenant=%s err=%s", feature, tenant_id, exc)
        sentry_sdk.capture_exception(exc)
