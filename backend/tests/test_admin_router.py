from unittest.mock import AsyncMock, patch

import pytest
from fastapi import BackgroundTasks, FastAPI
from fastapi.testclient import TestClient

from app.adapters.notifications import NotificationError
from app.config import settings
from app.dependencies.auth import UserContext, get_current_user
from app.routers import admin

_MODULE = "app.routers.admin"

_test_app = FastAPI()
_test_app.include_router(admin.router)
client = TestClient(_test_app)


@pytest.fixture(autouse=True)
def _clear_dependency_overrides():
    yield
    _test_app.dependency_overrides.clear()


def _as_user(role: str = "admin", tenant_id: str = "tenant_a", user_id: str = "user-1"):
    _test_app.dependency_overrides[get_current_user] = lambda: UserContext(
        user_id=user_id, tenant_id=tenant_id, role=role
    )


def test_sync_knowledge_base_without_api_key_header_returns_422():
    """缺 header 本身是驗證錯誤（比照 dependencies/auth.py 的 get_current_user 對缺
    Authorization header 的處理慣例，見 test_usage_router.py），驗證邏輯本身沒跑到。"""
    resp = client.post("/api/v1/admin/sync-knowledge-base")
    assert resp.status_code == 422


def test_sync_knowledge_base_with_wrong_api_key_returns_401():
    resp = client.post(
        "/api/v1/admin/sync-knowledge-base", headers={"X-API-Key": "wrong-key"}
    )
    assert resp.status_code == 401


def test_sync_knowledge_base_with_correct_api_key_dispatches_background_task():
    with (
        patch.object(settings, "sync_api_key", "correct-key"),
        patch.object(BackgroundTasks, "add_task") as mock_add_task,
    ):
        resp = client.post(
            "/api/v1/admin/sync-knowledge-base", headers={"X-API-Key": "correct-key"}
        )

    assert resp.status_code == 200
    assert resp.json() == {"status": "sync_started"}
    mock_add_task.assert_called_once()
    assert mock_add_task.call_args.args[0] is admin.run_incremental_sync


def test_test_notification_requires_admin_role():
    _as_user(role="viewer")

    resp = client.post("/api/v1/admin/test-notification")

    assert resp.status_code == 403


def test_test_notification_success_returns_ok():
    _as_user(role="admin")

    with patch(f"{_MODULE}.GmailAPINotificationAdapter") as MockAdapter:
        MockAdapter.return_value.send = AsyncMock()
        resp = client.post("/api/v1/admin/test-notification")

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
    MockAdapter.return_value.send.assert_called_once()


def test_test_notification_failure_returns_502():
    _as_user(role="admin")

    with patch(f"{_MODULE}.GmailAPINotificationAdapter") as MockAdapter:
        MockAdapter.return_value.send = AsyncMock(side_effect=NotificationError("憑證失效"))
        resp = client.post("/api/v1/admin/test-notification")

    assert resp.status_code == 502
