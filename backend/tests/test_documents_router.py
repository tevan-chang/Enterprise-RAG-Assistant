from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import documents

_MODULE = "app.routers.documents"

# 不掛 app.main 的 lifespan（zombie task cleanup 會真的連 Supabase），
# router 測試只需驗證 FastAPI 層邏輯，repo 一律 mock。
_test_app = FastAPI()
_test_app.include_router(documents.router)
client = TestClient(_test_app)


def test_reorganize_as_editor_upgrades_to_manually_verified():
    repo = MagicMock()
    repo.reorganize.return_value = {
        "id": "doc-1",
        "classification_status": "manually_verified",
        "final_categories": ["2026核心資料"],
    }

    with patch(f"{_MODULE}.DocumentsRepository", return_value=repo):
        resp = client.post(
            "/api/documents/reorganize",
            json={"document_id": "doc-1", "manual_categories": ["2026核心資料"]},
            headers={"X-User-Role": "editor"},
        )

    assert resp.status_code == 200
    assert resp.json()["classification_status"] == "manually_verified"
    repo.reorganize.assert_called_once_with("doc-1", ["2026核心資料"])


def test_reorganize_as_viewer_returns_403():
    with patch(f"{_MODULE}.DocumentsRepository") as MockRepo:
        resp = client.post(
            "/api/documents/reorganize",
            json={"document_id": "doc-1", "manual_categories": ["財務"]},
            headers={"X-User-Role": "viewer"},
        )

    assert resp.status_code == 403
    MockRepo.return_value.reorganize.assert_not_called()


def test_reorganize_missing_document_returns_404():
    repo = MagicMock()
    repo.reorganize.return_value = None

    with patch(f"{_MODULE}.DocumentsRepository", return_value=repo):
        resp = client.post(
            "/api/documents/reorganize",
            json={"document_id": "missing", "manual_categories": ["財務"]},
            headers={"X-User-Role": "admin"},
        )

    assert resp.status_code == 404


def test_unlock_as_admin_succeeds():
    repo = MagicMock()
    repo.unlock_bulk.return_value = [{"id": "doc-1"}, {"id": "doc-2"}]

    with patch(f"{_MODULE}.DocumentsRepository", return_value=repo):
        resp = client.post(
            "/api/documents/unlock",
            json={"document_ids": ["doc-1", "doc-2"]},
            headers={"X-User-Role": "admin"},
        )

    assert resp.status_code == 200
    assert resp.json()["unlocked_document_ids"] == ["doc-1", "doc-2"]


def test_unlock_as_non_admin_returns_403():
    """Day 5 DoD：unlock 端點對非 Admin 一律回傳 403（見 spec §3.2 `unlock` 動作限 Admin）。"""
    for role in ("editor", "viewer"):
        with patch(f"{_MODULE}.DocumentsRepository") as MockRepo:
            resp = client.post(
                "/api/documents/unlock",
                json={"document_ids": ["doc-1"]},
                headers={"X-User-Role": role},
            )

        assert resp.status_code == 403, f"role={role} 應被拒絕"
        MockRepo.return_value.unlock_bulk.assert_not_called()


def test_unlock_without_role_header_returns_422():
    resp = client.post("/api/documents/unlock", json={"document_ids": ["doc-1"]})

    assert resp.status_code == 422
