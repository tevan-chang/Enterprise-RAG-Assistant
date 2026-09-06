from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.dependencies.auth import UserContext, get_current_user
from app.routers import documents

_MODULE = "app.routers.documents"

# 不掛 app.main 的 lifespan（zombie task cleanup 會真的連 Supabase），
# router 測試只需驗證 FastAPI 層邏輯，repo 一律 mock。
_test_app = FastAPI()
_test_app.include_router(documents.router)
client = TestClient(_test_app)


@pytest.fixture(autouse=True)
def _clear_dependency_overrides():
    yield
    _test_app.dependency_overrides.clear()


def _as_user(tenant_id: str = "tenant_a", role: str = "admin", user_id: str = "user-1"):
    """用 dependency_overrides 覆寫 get_current_user，取代舊的 X-Tenant-Id/X-User-Role header。"""
    _test_app.dependency_overrides[get_current_user] = lambda: UserContext(
        user_id=user_id, tenant_id=tenant_id, role=role
    )


def test_list_documents_scoped_by_tenant():
    repo = MagicMock()
    repo.list_by_tenant.return_value = [
        {
            "id": "doc-1",
            "file_name": "a.pdf",
            "processing_status": "completed",
            "classification_status": "auto_labeled",
            "final_categories": ["財務"],
            "confidentiality": "internal",
            "updated_at": "2026-09-04T00:00:00+00:00",
        }
    ]
    _as_user(tenant_id="tenant_a")

    with patch(f"{_MODULE}.DocumentsRepository", return_value=repo):
        resp = client.get("/api/documents")

    assert resp.status_code == 200
    assert resp.json() == [
        {
            "document_id": "doc-1",
            "file_name": "a.pdf",
            "processing_status": "completed",
            "classification_status": "auto_labeled",
            "final_categories": ["財務"],
            "confidentiality": "internal",
            "updated_at": "2026-09-04T00:00:00+00:00",
        }
    ]
    repo.list_by_tenant.assert_called_once_with("tenant_a")


def test_list_documents_without_authorization_header_returns_422():
    resp = client.get("/api/documents")

    assert resp.status_code == 422


def test_reorganize_as_editor_upgrades_to_manually_verified():
    repo = MagicMock()
    repo.reorganize.return_value = {
        "id": "doc-1",
        "classification_status": "manually_verified",
        "final_categories": ["2026核心資料"],
    }
    _as_user(role="editor")

    with patch(f"{_MODULE}.DocumentsRepository", return_value=repo):
        resp = client.post(
            "/api/documents/reorganize",
            json={"document_id": "doc-1", "manual_categories": ["2026核心資料"]},
        )

    assert resp.status_code == 200
    assert resp.json()["classification_status"] == "manually_verified"
    repo.reorganize.assert_called_once_with("doc-1", ["2026核心資料"])


def test_reorganize_as_viewer_returns_403():
    _as_user(role="viewer")

    with patch(f"{_MODULE}.DocumentsRepository") as MockRepo:
        resp = client.post(
            "/api/documents/reorganize",
            json={"document_id": "doc-1", "manual_categories": ["財務"]},
        )

    assert resp.status_code == 403
    MockRepo.return_value.reorganize.assert_not_called()


def test_reorganize_missing_document_returns_404():
    repo = MagicMock()
    repo.reorganize.return_value = None
    _as_user(role="admin")

    with patch(f"{_MODULE}.DocumentsRepository", return_value=repo):
        resp = client.post(
            "/api/documents/reorganize",
            json={"document_id": "missing", "manual_categories": ["財務"]},
        )

    assert resp.status_code == 404


def test_unlock_as_admin_succeeds():
    repo = MagicMock()
    repo.unlock_bulk.return_value = [{"id": "doc-1"}, {"id": "doc-2"}]
    _as_user(role="admin")

    with patch(f"{_MODULE}.DocumentsRepository", return_value=repo):
        resp = client.post(
            "/api/documents/unlock",
            json={"document_ids": ["doc-1", "doc-2"]},
        )

    assert resp.status_code == 200
    assert resp.json()["unlocked_document_ids"] == ["doc-1", "doc-2"]


def test_unlock_as_non_admin_returns_403():
    """Day 5 DoD：unlock 端點對非 Admin 一律回傳 403（見 spec §3.2 `unlock` 動作限 Admin）。"""
    for role in ("editor", "viewer"):
        _as_user(role=role)
        with patch(f"{_MODULE}.DocumentsRepository") as MockRepo:
            resp = client.post(
                "/api/documents/unlock",
                json={"document_ids": ["doc-1"]},
            )

        assert resp.status_code == 403, f"role={role} 應被拒絕"
        MockRepo.return_value.unlock_bulk.assert_not_called()


def test_unlock_without_authorization_header_returns_422():
    resp = client.post("/api/documents/unlock", json={"document_ids": ["doc-1"]})

    assert resp.status_code == 422


def test_get_status_scoped_to_own_tenant():
    repo = MagicMock()
    repo.get.return_value = {
        "id": "doc-1",
        "tenant_id": "tenant_a",
        "file_name": "a.pdf",
        "processing_status": "embedding",
        "updated_at": "2026-09-04T00:00:00+00:00",
    }
    _as_user(tenant_id="tenant_a")

    with patch(f"{_MODULE}.DocumentsRepository", return_value=repo):
        resp = client.get("/api/documents/doc-1/status")

    assert resp.status_code == 200
    assert resp.json()["processing_status"] == "embedding"


def test_get_status_without_authorization_header_returns_422():
    resp = client.get("/api/documents/doc-1/status")

    assert resp.status_code == 422


def test_get_status_cross_tenant_returns_404():
    """documents repo 用 service_role key bypass RLS，tenant 隔離必須在這層擋
    （見 CLAUDE.md 雙層權限隔離）；缺這道檢查等於任何人知道 document_id 就能查到
    其他租戶的處理狀態，是 spec §11「RLS Policy 正確性錯誤」風險項對應的實際漏洞。
    """
    repo = MagicMock()
    repo.get.return_value = {
        "id": "doc-1",
        "tenant_id": "tenant_b",
        "file_name": "b.pdf",
        "processing_status": "completed",
        "updated_at": "2026-09-04T00:00:00+00:00",
    }
    _as_user(tenant_id="tenant_a")

    with patch(f"{_MODULE}.DocumentsRepository", return_value=repo):
        resp = client.get("/api/documents/doc-1/status")

    assert resp.status_code == 404


def test_get_status_missing_document_returns_404():
    repo = MagicMock()
    repo.get.return_value = None
    _as_user(tenant_id="tenant_a")

    with patch(f"{_MODULE}.DocumentsRepository", return_value=repo):
        resp = client.get("/api/documents/missing/status")

    assert resp.status_code == 404


def test_get_chunks_scoped_to_own_tenant():
    documents_repo = MagicMock()
    documents_repo.get.return_value = _fake_doc()
    chunks_repo = MagicMock()
    chunks_repo.list_by_document.return_value = [
        {"chunk_index": 0, "page_number": 1, "content": "第一段", "token_count": 10, "sheet_name": None, "cell_range": None}
    ]
    _as_user(tenant_id="tenant_a", role="admin")

    with (
        patch(f"{_MODULE}.DocumentsRepository", return_value=documents_repo),
        patch(f"{_MODULE}.ChunksRepository", return_value=chunks_repo),
    ):
        resp = client.get("/api/documents/doc-1/chunks")

    assert resp.status_code == 200
    assert resp.json()[0]["content"] == "第一段"


def test_get_chunks_without_authorization_header_returns_422():
    resp = client.get("/api/documents/doc-1/chunks")

    assert resp.status_code == 422


def test_get_chunks_cross_tenant_returns_404():
    """比照 `/citation`：chunks 回傳完整解析內文，tenant 隔離必須在 Python 層做
    （repo 用 service_role key bypass RLS，見 CLAUDE.md 雙層權限隔離）。"""
    documents_repo = MagicMock()
    documents_repo.get.return_value = _fake_doc(tenant_id="tenant_b")
    _as_user(tenant_id="tenant_a", role="admin")

    with (
        patch(f"{_MODULE}.DocumentsRepository", return_value=documents_repo),
        patch(f"{_MODULE}.ChunksRepository") as MockChunksRepo,
    ):
        resp = client.get("/api/documents/doc-1/chunks")

    assert resp.status_code == 404
    MockChunksRepo.return_value.list_by_document.assert_not_called()


def test_get_chunks_missing_document_returns_404():
    documents_repo = MagicMock()
    documents_repo.get.return_value = None
    _as_user(tenant_id="tenant_a", role="admin")

    with patch(f"{_MODULE}.DocumentsRepository", return_value=documents_repo):
        resp = client.get("/api/documents/missing/chunks")

    assert resp.status_code == 404


def test_get_chunks_as_viewer_on_restricted_document_returns_403():
    """chunks 敏感度與 citation 相同（完整內文），viewer 對 restricted 文件比照擋下。"""
    documents_repo = MagicMock()
    documents_repo.get.return_value = _fake_doc(confidentiality="restricted")
    _as_user(tenant_id="tenant_a", role="viewer")

    with (
        patch(f"{_MODULE}.DocumentsRepository", return_value=documents_repo),
        patch(f"{_MODULE}.ChunksRepository") as MockChunksRepo,
    ):
        resp = client.get("/api/documents/doc-1/chunks")

    assert resp.status_code == 403
    MockChunksRepo.return_value.list_by_document.assert_not_called()


def _fake_doc(**overrides):
    doc = {
        "id": "doc-1",
        "tenant_id": "tenant_a",
        "file_name": "財報.pdf",
        "confidentiality": "internal",
    }
    doc.update(overrides)
    return doc


def test_get_citation_by_page_number_returns_joined_chunk_content():
    documents_repo = MagicMock()
    documents_repo.get.return_value = _fake_doc()
    chunks_repo = MagicMock()
    chunks_repo.list_by_location.return_value = [
        {"chunk_index": 0, "content": "第一段"},
        {"chunk_index": 1, "content": "第二段"},
    ]
    _as_user(tenant_id="tenant_a", role="admin")

    with (
        patch(f"{_MODULE}.DocumentsRepository", return_value=documents_repo),
        patch(f"{_MODULE}.ChunksRepository", return_value=chunks_repo),
    ):
        resp = client.get(
            "/api/documents/doc-1/citation",
            params={"page_number": 3},
        )

    assert resp.status_code == 200
    assert resp.json() == {
        "document_id": "doc-1",
        "file_name": "財報.pdf",
        "page_number": 3,
        "sheet_name": None,
        "cell_range": None,
        "content": "第一段\n\n第二段",
    }
    chunks_repo.list_by_location.assert_called_once_with(
        "doc-1", page_number=3, sheet_name=None, cell_range=None
    )


def test_get_citation_by_sheet_and_cell_range():
    documents_repo = MagicMock()
    documents_repo.get.return_value = _fake_doc(file_name="2026Q2.xlsx")
    chunks_repo = MagicMock()
    chunks_repo.list_by_location.return_value = [{"chunk_index": 0, "content": "B2:D15 內容"}]
    _as_user(tenant_id="tenant_a", role="admin")

    with (
        patch(f"{_MODULE}.DocumentsRepository", return_value=documents_repo),
        patch(f"{_MODULE}.ChunksRepository", return_value=chunks_repo),
    ):
        resp = client.get(
            "/api/documents/doc-1/citation",
            params={"sheet_name": "營收明細", "cell_range": "B2:D15"},
        )

    assert resp.status_code == 200
    assert resp.json()["content"] == "B2:D15 內容"


def test_get_citation_without_location_params_returns_422():
    _as_user(tenant_id="tenant_a", role="admin")

    resp = client.get("/api/documents/doc-1/citation")

    assert resp.status_code == 422


def test_get_citation_cross_tenant_returns_404():
    """documents repo 用 service_role key bypass RLS，tenant 隔離必須在這層擋（見 CLAUDE.md 雙層權限隔離）。"""
    documents_repo = MagicMock()
    documents_repo.get.return_value = _fake_doc(tenant_id="tenant_b")
    _as_user(tenant_id="tenant_a", role="admin")

    with patch(f"{_MODULE}.DocumentsRepository", return_value=documents_repo):
        resp = client.get(
            "/api/documents/doc-1/citation",
            params={"page_number": 3},
        )

    assert resp.status_code == 404


def test_get_citation_missing_document_returns_404():
    documents_repo = MagicMock()
    documents_repo.get.return_value = None
    _as_user(tenant_id="tenant_a", role="admin")

    with patch(f"{_MODULE}.DocumentsRepository", return_value=documents_repo):
        resp = client.get(
            "/api/documents/missing/citation",
            params={"page_number": 3},
        )

    assert resp.status_code == 404


def test_get_citation_as_viewer_on_restricted_document_returns_403():
    documents_repo = MagicMock()
    documents_repo.get.return_value = _fake_doc(confidentiality="restricted")
    _as_user(tenant_id="tenant_a", role="viewer")

    with patch(f"{_MODULE}.DocumentsRepository", return_value=documents_repo):
        resp = client.get(
            "/api/documents/doc-1/citation",
            params={"page_number": 3},
        )

    assert resp.status_code == 403


def test_get_citation_no_matching_chunks_returns_404():
    documents_repo = MagicMock()
    documents_repo.get.return_value = _fake_doc()
    chunks_repo = MagicMock()
    chunks_repo.list_by_location.return_value = []
    _as_user(tenant_id="tenant_a", role="admin")

    with (
        patch(f"{_MODULE}.DocumentsRepository", return_value=documents_repo),
        patch(f"{_MODULE}.ChunksRepository", return_value=chunks_repo),
    ):
        resp = client.get(
            "/api/documents/doc-1/citation",
            params={"page_number": 99},
        )

    assert resp.status_code == 404
