import asyncio
import base64
from abc import ABC, abstractmethod
from email.mime.text import MIMEText

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.config import settings

_GMAIL_TOKEN_URI = "https://oauth2.googleapis.com/token"
_GMAIL_SEND_SCOPES = ["https://www.googleapis.com/auth/gmail.send"]


class NotificationError(Exception):
    pass


class BaseNotificationService(ABC):
    @abstractmethod
    async def send(self, to: str, subject: str, html_content: str) -> None:
        """寄送 HTML 郵件，失敗時拋出 NotificationError（呼叫端決定要吞掉還是往外拋，
        見 services/notifications.py 的 send_notification 吞例外、routers/admin.py 的
        test-notification 端點刻意讓例外往外拋兩種不同用法）"""


class GmailAPINotificationAdapter(BaseNotificationService):
    """經 google.oauth2 讀環境變數載入 GCP Credentials，走 refresh_token 流程（見 spec §2.1）。

    憑證一律讀 Settings（來源是環境變數），不硬編碼於 repo（見 Guardrail #11）。
    googleapiclient 是同步阻塞 API，包一層 asyncio.to_thread 避免卡住 event loop。
    """

    def _get_service(self):
        credentials = Credentials(
            None,
            refresh_token=settings.gmail_oauth_refresh_token,
            token_uri=_GMAIL_TOKEN_URI,
            client_id=settings.gmail_oauth_client_id,
            client_secret=settings.gmail_oauth_client_secret,
            scopes=_GMAIL_SEND_SCOPES,
        )
        return build("gmail", "v1", credentials=credentials)

    def _send_sync(self, to: str, subject: str, html_content: str) -> None:
        message = MIMEText(html_content, "html", "utf-8")
        message["to"] = to
        message["subject"] = subject
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")

        try:
            self._get_service().users().messages().send(userId="me", body={"raw": raw}).execute()
        except HttpError as exc:
            raise NotificationError(f"Gmail API 寄信失敗: {exc}") from exc

    async def send(self, to: str, subject: str, html_content: str) -> None:
        if not (settings.gmail_oauth_client_id and settings.gmail_oauth_client_secret and settings.gmail_oauth_refresh_token):
            raise NotificationError("Gmail OAuth 憑證未設定（GMAIL_OAUTH_CLIENT_ID/SECRET/REFRESH_TOKEN）")
        await asyncio.to_thread(self._send_sync, to, subject, html_content)
