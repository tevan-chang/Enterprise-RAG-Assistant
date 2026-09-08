from unittest.mock import MagicMock, patch

from app.services.token_usage import record_usage

_MODULE = "app.services.token_usage"


def test_record_usage_delegates_to_repository():
    repo = MagicMock()

    record_usage(
        tenant_id="tenant_a",
        user_id="user-1",
        feature="chat",
        model="gpt-4o",
        prompt_tokens=10,
        completion_tokens=5,
        repo=repo,
    )

    repo.record.assert_called_once_with(
        tenant_id="tenant_a",
        user_id="user-1",
        feature="chat",
        model="gpt-4o",
        prompt_tokens=10,
        completion_tokens=5,
    )


def test_record_usage_swallows_repository_failure_and_reports_sentry():
    """DoD 關鍵斷言：記錄失敗不可讓例外冒出去影響呼叫端（chat/report 主流程）。"""
    repo = MagicMock()
    repo.record.side_effect = RuntimeError("supabase down")

    with patch(f"{_MODULE}.sentry_sdk") as mock_sentry:
        record_usage(
            tenant_id="tenant_a",
            user_id="user-1",
            feature="chat",
            model="gpt-4o",
            prompt_tokens=10,
            completion_tokens=5,
            repo=repo,
        )

    mock_sentry.capture_exception.assert_called_once()


def test_record_usage_uses_default_repository_when_not_injected():
    with patch(f"{_MODULE}.TokenUsageRepository") as MockRepo:
        record_usage(
            tenant_id="tenant_a",
            user_id="user-1",
            feature="embedding",
            model="text-embedding-3-small",
            prompt_tokens=10,
            completion_tokens=0,
        )

    MockRepo.return_value.record.assert_called_once()
