from unittest.mock import AsyncMock, patch

import pytest

from app.config import settings
from app.services.notifications import (
    DOCUMENT_PROCESSED,
    FLAG_FOR_REVIEW,
    RAG_SYNC_COMPLETED,
    _build_content,
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
