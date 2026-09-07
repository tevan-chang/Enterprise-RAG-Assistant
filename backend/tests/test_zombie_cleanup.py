from unittest.mock import MagicMock, patch

from app.services.zombie_cleanup import cleanup_zombie_tasks

_MODULE = "app.services.zombie_cleanup"


def test_cleanup_zombie_tasks_marks_failed_and_reports_to_sentry():
    repo = MagicMock()
    repo.find_zombie_tasks.return_value = [
        {"id": "doc-1", "file_name": "a.pdf", "processing_status": "parsing", "updated_at": "2026-09-01T00:00:00Z"}
    ]

    with (
        patch(f"{_MODULE}.DocumentsRepository", return_value=repo),
        patch(f"{_MODULE}.sentry_sdk") as mock_sentry,
    ):
        count = cleanup_zombie_tasks()

    assert count == 1
    repo.mark_failed_bulk.assert_called_once_with(["doc-1"])
    mock_sentry.capture_message.assert_called_once()
    assert "doc-1" in mock_sentry.capture_message.call_args.args[0]


def test_cleanup_zombie_tasks_returns_zero_when_none_found():
    repo = MagicMock()
    repo.find_zombie_tasks.return_value = []

    with (
        patch(f"{_MODULE}.DocumentsRepository", return_value=repo),
        patch(f"{_MODULE}.sentry_sdk") as mock_sentry,
    ):
        count = cleanup_zombie_tasks()

    assert count == 0
    repo.mark_failed_bulk.assert_not_called()
    mock_sentry.capture_message.assert_not_called()
