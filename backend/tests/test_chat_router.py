from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.dependencies.auth import UserContext, get_current_user
from app.routers import chat

_MODULE = "app.routers.chat"

_test_app = FastAPI()
_test_app.include_router(chat.router)
client = TestClient(_test_app)


@pytest.fixture(autouse=True)
def _clear_dependency_overrides():
    yield
    _test_app.dependency_overrides.clear()


def _as_user(tenant_id: str = "tenant_a", role: str = "viewer", user_id: str = "user-1"):
    _test_app.dependency_overrides[get_current_user] = lambda: UserContext(
        user_id=user_id, tenant_id=tenant_id, role=role
    )


async def _fake_stream(**kwargs):
    yield 'event: message\ndata: {"delta": "你好"}\n\n'
    yield "event: done\ndata: {}\n\n"


def test_query_streams_sse_response_and_forwards_identity():
    captured_kwargs = {}

    async def _capturing_stream(**kwargs):
        captured_kwargs.update(kwargs)
        async for event in _fake_stream():
            yield event

    _as_user(tenant_id="tenant_a", role="viewer")

    with patch(f"{_MODULE}.stream_chat_response", side_effect=_capturing_stream):
        resp = client.post("/api/query", json={"query": "測試問題"})

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    assert resp.text == 'event: message\ndata: {"delta": "你好"}\n\n' + "event: done\ndata: {}\n\n"
    assert captured_kwargs == {
        "query": "測試問題",
        "tenant_id": "tenant_a",
        "role": "viewer",
        "departments": None,
        "top_k": None,
    }


def test_query_without_authorization_header_returns_422():
    resp = client.post("/api/query", json={"query": "測試問題"})

    assert resp.status_code == 422


def test_query_with_blank_query_returns_422():
    _as_user(tenant_id="tenant_a", role="viewer")

    resp = client.post("/api/query", json={"query": "   "})

    assert resp.status_code == 422
