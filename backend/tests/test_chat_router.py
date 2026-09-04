from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import chat

_MODULE = "app.routers.chat"

_test_app = FastAPI()
_test_app.include_router(chat.router)
client = TestClient(_test_app)


async def _fake_stream(**kwargs):
    yield 'event: message\ndata: {"delta": "你好"}\n\n'
    yield "event: done\ndata: {}\n\n"


def test_query_streams_sse_response_and_forwards_identity_headers():
    captured_kwargs = {}

    async def _capturing_stream(**kwargs):
        captured_kwargs.update(kwargs)
        async for event in _fake_stream():
            yield event

    with patch(f"{_MODULE}.stream_chat_response", side_effect=_capturing_stream):
        resp = client.post(
            "/api/query",
            json={"query": "測試問題"},
            headers={"X-Tenant-Id": "tenant_a", "X-User-Role": "viewer"},
        )

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


def test_query_without_tenant_header_returns_422():
    resp = client.post("/api/query", json={"query": "測試問題"}, headers={"X-User-Role": "viewer"})

    assert resp.status_code == 422


def test_query_with_blank_query_returns_422():
    resp = client.post(
        "/api/query",
        json={"query": "   "},
        headers={"X-Tenant-Id": "tenant_a", "X-User-Role": "viewer"},
    )

    assert resp.status_code == 422
