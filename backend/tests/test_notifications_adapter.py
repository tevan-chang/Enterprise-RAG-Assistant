import base64
import email
from email.header import decode_header
from unittest.mock import MagicMock, patch

import pytest

from app.adapters.notifications import GmailAPINotificationAdapter, NotificationError

_MODULE = "app.adapters.notifications"


@pytest.fixture(autouse=True)
def _configure_gmail_settings():
    with patch(f"{_MODULE}.settings") as mock_settings:
        mock_settings.gmail_oauth_client_id = "client-id"
        mock_settings.gmail_oauth_client_secret = "client-secret"
        mock_settings.gmail_oauth_refresh_token = "refresh-token"
        yield mock_settings


async def test_send_builds_mime_message_and_calls_gmail_send():
    mock_service = MagicMock()
    send_execute = mock_service.users.return_value.messages.return_value.send.return_value.execute

    with (
        patch(f"{_MODULE}.Credentials") as MockCredentials,
        patch(f"{_MODULE}.build", return_value=mock_service) as mock_build,
    ):
        await GmailAPINotificationAdapter().send("admin@example.com", "測試主旨", "<p>內文</p>")

    MockCredentials.assert_called_once()
    mock_build.assert_called_once_with("gmail", "v1", credentials=MockCredentials.return_value)

    send_call = mock_service.users.return_value.messages.return_value.send
    send_call.assert_called_once()
    _, kwargs = send_call.call_args
    assert kwargs["userId"] == "me"
    raw = kwargs["body"]["raw"]
    parsed = email.message_from_bytes(base64.urlsafe_b64decode(raw.encode("ascii")))
    assert parsed["to"] == "admin@example.com"
    subject_parts = decode_header(parsed["subject"])
    subject_text = "".join(
        part.decode(enc or "utf-8") if isinstance(part, bytes) else part for part, enc in subject_parts
    )
    assert subject_text == "測試主旨"
    body = parsed.get_payload(decode=True).decode(parsed.get_content_charset() or "utf-8")
    assert body == "<p>內文</p>"
    send_execute.assert_called_once()


async def test_send_raises_notification_error_when_credentials_missing(_configure_gmail_settings):
    _configure_gmail_settings.gmail_oauth_refresh_token = ""

    with pytest.raises(NotificationError):
        await GmailAPINotificationAdapter().send("admin@example.com", "主旨", "<p>內文</p>")


async def test_send_wraps_http_error_as_notification_error():
    from googleapiclient.errors import HttpError

    http_error = HttpError(resp=MagicMock(status=500), content=b"boom")
    mock_service = MagicMock()
    mock_service.users.return_value.messages.return_value.send.return_value.execute.side_effect = http_error

    with (
        patch(f"{_MODULE}.Credentials"),
        patch(f"{_MODULE}.build", return_value=mock_service),
    ):
        with pytest.raises(NotificationError):
            await GmailAPINotificationAdapter().send("admin@example.com", "主旨", "<p>內文</p>")
