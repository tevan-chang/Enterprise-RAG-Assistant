from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import settings
from app.services.notifications import (
    DOCUMENT_PROCESSED,
    FLAG_FOR_REVIEW,
    RAG_SYNC_COMPLETED,
    _build_content,
    _resolve_uploader_email,
    send_notification,
)

_MODULE = "app.services.notifications"


def test_build_content_document_processed_includes_file_name_and_document_id():
    subject, html = _build_content(
        DOCUMENT_PROCESSED, {"document_id": "doc-1", "file_name": "q3.pdf"}
    )
    assert "q3.pdf" in subject
    assert "q3.pdf" in html
    assert "doc-1" in html


def test_build_content_flag_for_review_includes_document_id():
    subject, html = _build_content(FLAG_FOR_REVIEW, {"document_id": "doc-1"})
    assert "待審查" in subject
    assert "doc-1" in html


def test_build_content_rag_sync_completed_includes_summary():
    subject, html = _build_content(RAG_SYNC_COMPLETED, {"zombie_marked_failed": 3})
    assert "同步" in subject
    assert "3" in html


def test_build_content_unknown_scenario_raises():
    with pytest.raises(ValueError):
        _build_content("UNKNOWN", {})


async def test_send_notification_delegates_to_adapter():
    adapter = AsyncMock()

    await send_notification(DOCUMENT_PROCESSED, {"document_id": "doc-1", "file_name": "q3.pdf"}, adapter=adapter)

    adapter.send.assert_called_once()
    args = adapter.send.call_args.args
    assert args[0] == settings.admin_notification_email
    assert "q3.pdf" in args[1]


async def test_send_notification_swallows_adapter_failure_and_reports_sentry():
    """DoD 關鍵斷言：Gmail 寄送失敗不可讓例外冒出去影響呼叫端主流程。"""
    adapter = AsyncMock()
    adapter.send.side_effect = RuntimeError("gmail api down")

    with patch(f"{_MODULE}.sentry_sdk") as mock_sentry:
        await send_notification(FLAG_FOR_REVIEW, {"document_id": "doc-1"}, adapter=adapter)

    mock_sentry.capture_exception.assert_called_once()


async def test_send_notification_uses_default_adapter_when_not_injected():
    with patch(f"{_MODULE}.GmailAPINotificationAdapter") as MockAdapter:
        MockAdapter.return_value.send = AsyncMock()
        await send_notification(RAG_SYNC_COMPLETED, {"zombie_marked_failed": 0})

    MockAdapter.return_value.send.assert_called_once()


async def test_send_notification_ignores_user_id_when_dynamic_recipient_disabled():
    """旗標預設關閉：即使 context 帶 user_id，收件人仍是 admin_notification_email。"""
    adapter = AsyncMock()

    await send_notification(
        DOCUMENT_PROCESSED,
        {"document_id": "doc-1", "file_name": "q3.pdf", "user_id": "user-1"},
        adapter=adapter,
    )

    assert adapter.send.call_args.args[0] == settings.admin_notification_email


async def test_send_notification_uses_uploader_email_when_dynamic_recipient_enabled():
    adapter = AsyncMock()

    with (
        patch.object(settings, "use_dynamic_notification_recipient", True),
        patch(f"{_MODULE}._resolve_uploader_email", return_value="uploader@example.com") as mock_resolve,
    ):
        await send_notification(
            DOCUMENT_PROCESSED,
            {"document_id": "doc-1", "file_name": "q3.pdf", "user_id": "user-1"},
            adapter=adapter,
        )

    mock_resolve.assert_called_once_with("user-1")
    assert adapter.send.call_args.args[0] == "uploader@example.com"


async def test_send_notification_falls_back_to_admin_email_when_lookup_fails():
    adapter = AsyncMock()

    with (
        patch.object(settings, "use_dynamic_notification_recipient", True),
        patch(f"{_MODULE}._resolve_uploader_email", return_value=None),
    ):
        await send_notification(
            DOCUMENT_PROCESSED,
            {"document_id": "doc-1", "file_name": "q3.pdf", "user_id": "user-1"},
            adapter=adapter,
        )

    assert adapter.send.call_args.args[0] == settings.admin_notification_email


async def test_send_notification_falls_back_to_admin_email_when_no_user_id():
    adapter = AsyncMock()

    with (
        patch.object(settings, "use_dynamic_notification_recipient", True),
        patch(f"{_MODULE}._resolve_uploader_email") as mock_resolve,
    ):
        await send_notification(
            DOCUMENT_PROCESSED,
            {"document_id": "doc-1", "file_name": "q3.pdf"},
            adapter=adapter,
        )

    mock_resolve.assert_not_called()
    assert adapter.send.call_args.args[0] == settings.admin_notification_email


def test_resolve_uploader_email_returns_email_on_success():
    mock_client = MagicMock()
    mock_client.auth.admin.get_user_by_id.return_value.user.email = "uploader@example.com"

    with patch(f"{_MODULE}.get_supabase_client", return_value=mock_client):
        result = _resolve_uploader_email("user-1")

    assert result == "uploader@example.com"
    mock_client.auth.admin.get_user_by_id.assert_called_once_with("user-1")


def test_resolve_uploader_email_returns_none_when_lookup_raises():
    mock_client = MagicMock()
    mock_client.auth.admin.get_user_by_id.side_effect = RuntimeError("not found")

    with patch(f"{_MODULE}.get_supabase_client", return_value=mock_client):
        result = _resolve_uploader_email("user-1")

    assert result is None
