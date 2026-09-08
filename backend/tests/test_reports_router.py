from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.dependencies.auth import UserContext, get_current_user
from app.routers import reports

_MODULE = "app.routers.reports"

# 不掛 app.main（會觸發 init_sentry() 與 lifespan zombie cleanup），router 測試只驗證
# FastAPI 層邏輯，service 一律 mock（比照 test_chat_router.py / test_documents_router.py）。
_test_app = FastAPI()
_test_app.include_router(reports.router)
client = TestClient(_test_app)


@pytest.fixture(autouse=True)
def _clear_dependency_overrides():
    yield
    _test_app.dependency_overrides.clear()


def _as_user(tenant_id: str = "tenant_a", role: str = "admin", user_id: str = "user-1"):
    _test_app.dependency_overrides[get_current_user] = lambda: UserContext(
        user_id=user_id, tenant_id=tenant_id, role=role
    )


def test_generate_report_returns_content_and_tool_calls_and_forwards_identity():
    _as_user(tenant_id="tenant_a", role="editor")
    fake_result = {
        "content": "總業績為 400000",
        "tool_calls": [
            {
                "tool": "compute_table_metric",
                "arguments": '{"document_id": "doc-1"}',
                "result": {"status": "success", "result": 400000.0},
            }
        ],
    }

    with patch(f"{_MODULE}.run_report_tool_calling", new=AsyncMock(return_value=fake_result)) as mock_run:
        resp = client.post("/api/reports/generate", json={"query": "業績加總多少"})

    assert resp.status_code == 200
    assert resp.json() == fake_result
    mock_run.assert_awaited_once_with(
        query="業績加總多少", tenant_id="tenant_a", role="editor", user_id="user-1", departments=None
    )


def test_generate_report_forwards_departments():
    """比照 test_chat_router.py 的 departments 轉發驗證：router 需把 payload.departments
    轉發給 service，避免 report_tools.py 的 query_documents 收不到 department 過濾條件。
    """
    _as_user(tenant_id="tenant_a", role="editor")
    captured_kwargs = {}

    async def _capturing_run(**kwargs):
        captured_kwargs.update(kwargs)
        return {"content": "報告內容", "tool_calls": []}

    with patch(f"{_MODULE}.run_report_tool_calling", side_effect=_capturing_run):
        resp = client.post(
            "/api/reports/generate",
            json={"query": "業績加總多少", "departments": ["財務部"]},
        )

    assert resp.status_code == 200
    assert captured_kwargs == {
        "query": "業績加總多少",
        "tenant_id": "tenant_a",
        "role": "editor",
        "user_id": "user-1",
        "departments": ["財務部"],
    }


def test_generate_report_without_authorization_header_returns_422():
    resp = client.post("/api/reports/generate", json={"query": "業績加總多少"})

    assert resp.status_code == 422


def test_generate_report_with_blank_query_returns_422():
    _as_user()

    resp = client.post("/api/reports/generate", json={"query": "   "})

    assert resp.status_code == 422


def test_generate_report_defaults_content_to_empty_string_when_none():
    """LLM 只呼叫 tool 沒有文字內容時 message.content 可能是 None，回應仍須是合法字串。"""
    _as_user()
    fake_result = {"content": None, "tool_calls": []}

    with patch(f"{_MODULE}.run_report_tool_calling", new=AsyncMock(return_value=fake_result)):
        resp = client.post("/api/reports/generate", json={"query": "測試"})

    assert resp.status_code == 200
    assert resp.json()["content"] == ""
