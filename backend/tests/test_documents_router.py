import hashlib
from unittest.mock import MagicMock, patch

import pytest
from fastapi import BackgroundTasks, FastAPI
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


def test_upload_as_viewer_returns_403():
    """spec §3.2：Viewer 僅限提問與檢索，無權上傳（比照 reorganize 的 require_role 寫法）。"""
    _as_user(role="viewer")

    with (
        patch(f"{_MODULE}.DocumentsRepository") as MockRepo,
        patch.object(BackgroundTasks, "add_task") as mock_add_task,
    ):
        resp = client.post(
            "/api/documents/upload",
            files={"file": ("a.pdf", b"%PDF-1.4 fake", "application/pdf")},
        )

    assert resp.status_code == 403
    MockRepo.return_value.create.assert_not_called()
    mock_add_task.assert_not_called()


def test_upload_as_editor_or_admin_succeeds():
    for role in ("editor", "admin"):
        repo = MagicMock()
        repo.get_by_content_hash.return_value = None
        repo.get_by_file_name.return_value = None
        repo.create.return_value = {"id": "doc-1", "processing_status": "parsing"}
        _as_user(role=role, tenant_id="tenant_a")

        with (
            patch(f"{_MODULE}.DocumentsRepository", return_value=repo),
            patch.object(BackgroundTasks, "add_task"),
        ):
            resp = client.post(
                "/api/documents/upload",
                files={"file": ("a.pdf", b"%PDF-1.4 fake", "application/pdf")},
            )

        assert resp.status_code == 200, f"role={role} 應允許上傳"
        assert resp.json() == {"document_id": "doc-1", "processing_status": "parsing"}


def test_upload_rejects_unsupported_content_type_returns_422():
    _as_user(role="editor")

    with (
        patch(f"{_MODULE}.DocumentsRepository") as MockRepo,
        patch.object(BackgroundTasks, "add_task") as mock_add_task,
    ):
        resp = client.post(
            "/api/documents/upload",
            files={
                "file": (
                    "a.docx",
                    b"fake docx bytes",
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            },
        )

    assert resp.status_code == 422
    MockRepo.return_value.create.assert_not_called()
    mock_add_task.assert_not_called()


def test_upload_pdf_triggers_background_task_with_correct_pipeline():
    repo = MagicMock()
    repo.get_by_content_hash.return_value = None
    repo.get_by_file_name.return_value = None
    repo.create.return_value = {"id": "doc-1", "processing_status": "parsing"}
    _as_user(role="editor", tenant_id="tenant_a")

    with (
        patch(f"{_MODULE}.DocumentsRepository", return_value=repo),
        patch.object(BackgroundTasks, "add_task") as mock_add_task,
    ):
        resp = client.post(
            "/api/documents/upload",
            files={"file": ("a.pdf", b"%PDF-1.4 fake", "application/pdf")},
        )

    assert resp.status_code == 200
    mock_add_task.assert_called_once()
    args, kwargs = mock_add_task.call_args
    assert args[0] is documents.process_pdf_document
    assert kwargs == {
        "document_id": "doc-1",
        "tenant_id": "tenant_a",
        "file_bytes": b"%PDF-1.4 fake",
        "file_name": "a.pdf",
    }


def test_upload_xlsx_triggers_background_task_with_correct_pipeline():
    repo = MagicMock()
    repo.get_by_content_hash.return_value = None
    repo.get_by_file_name.return_value = None
    repo.create.return_value = {"id": "doc-2", "processing_status": "parsing"}
    _as_user(role="admin", tenant_id="tenant_a")

    with (
        patch(f"{_MODULE}.DocumentsRepository", return_value=repo),
        patch.object(BackgroundTasks, "add_task") as mock_add_task,
    ):
        resp = client.post(
            "/api/documents/upload",
            files={"file": ("b.xlsx", b"fake xlsx bytes", documents._XLSX_CONTENT_TYPE)},
        )

    assert resp.status_code == 200
    mock_add_task.assert_called_once()
    args, kwargs = mock_add_task.call_args
    assert args[0] is documents.process_xlsx_document
    assert kwargs == {
        "document_id": "doc-2",
        "tenant_id": "tenant_a",
        "file_bytes": b"fake xlsx bytes",
        "file_name": "b.xlsx",
    }


def test_upload_without_authorization_header_returns_422():
    resp = client.post(
        "/api/documents/upload",
        files={"file": ("a.pdf", b"%PDF-1.4 fake", "application/pdf")},
    )

    assert resp.status_code == 422


def test_upload_duplicate_content_hash_returns_409():
    """同一份檔案（內容 hash 相同）第二次上傳直接擋下，不建立新文件、不觸發 pipeline。"""
    repo = MagicMock()
    repo.get_by_content_hash.return_value = {"id": "doc-existing", "file_name": "a.pdf"}
    _as_user(role="editor", tenant_id="tenant_a")

    with (
        patch(f"{_MODULE}.DocumentsRepository", return_value=repo),
        patch.object(BackgroundTasks, "add_task") as mock_add_task,
    ):
        resp = client.post(
            "/api/documents/upload",
            files={"file": ("a.pdf", b"%PDF-1.4 fake", "application/pdf")},
        )

    assert resp.status_code == 409
    assert resp.json()["detail"] == {
        "message": "相同內容的文件已存在，略過重複上傳",
        "document_id": "doc-existing",
        "file_name": "a.pdf",
    }
    repo.create.assert_not_called()
    mock_add_task.assert_not_called()


def test_upload_duplicate_content_different_filename_still_returns_409():
    """證明比對邏輯是 file_content_hash 而非檔名：檔名不同、內容相同一樣被擋。"""
    repo = MagicMock()
    repo.get_by_content_hash.return_value = {"id": "doc-existing", "file_name": "original.pdf"}
    _as_user(role="editor", tenant_id="tenant_a")

    with (
        patch(f"{_MODULE}.DocumentsRepository", return_value=repo),
        patch.object(BackgroundTasks, "add_task") as mock_add_task,
    ):
        resp = client.post(
            "/api/documents/upload",
            files={"file": ("renamed.pdf", b"%PDF-1.4 fake", "application/pdf")},
        )

    assert resp.status_code == 409
    assert resp.json()["detail"]["document_id"] == "doc-existing"
    repo.create.assert_not_called()
    mock_add_task.assert_not_called()


def test_upload_filename_collision_returns_409():
    """檔名相同、內容 hash 不同：無法自動判斷是版本更新還是同名的不同文件，
    交由使用者選擇，不自動建立新文件（見 spec §4.3 延伸）。"""
    repo = MagicMock()
    repo.get_by_content_hash.return_value = None
    repo.get_by_file_name.return_value = {
        "id": "doc-existing",
        "file_name": "a.pdf",
        "classification_status": "manually_verified",
    }
    _as_user(role="editor", tenant_id="tenant_a")

    with (
        patch(f"{_MODULE}.DocumentsRepository", return_value=repo),
        patch.object(BackgroundTasks, "add_task") as mock_add_task,
    ):
        resp = client.post(
            "/api/documents/upload",
            files={"file": ("a.pdf", b"different content", "application/pdf")},
        )

    assert resp.status_code == 409
    assert resp.json()["detail"] == {
        "reason": "filename_exists",
        "message": "已有相同檔名的文件，請選擇覆蓋既有文件或改用其他檔名",
        "document_id": "doc-existing",
        "file_name": "a.pdf",
        "classification_status": "manually_verified",
    }
    repo.create.assert_not_called()
    mock_add_task.assert_not_called()


def test_upload_with_force_skips_filename_collision_check():
    """使用者在前端選擇「仍要新建」時帶 force=true，略過檔名碰撞檢查，正常建立新文件。"""
    repo = MagicMock()
    repo.get_by_content_hash.return_value = None
    repo.create.return_value = {"id": "doc-new", "processing_status": "parsing"}
    _as_user(role="editor", tenant_id="tenant_a")

    with (
        patch(f"{_MODULE}.DocumentsRepository", return_value=repo),
        patch.object(BackgroundTasks, "add_task") as mock_add_task,
    ):
        resp = client.post(
            "/api/documents/upload",
            params={"force": "true"},
            files={"file": ("a.pdf", b"different content", "application/pdf")},
        )

    assert resp.status_code == 200
    assert resp.json() == {"document_id": "doc-new", "processing_status": "parsing"}
    repo.get_by_file_name.assert_not_called()
    mock_add_task.assert_called_once()


def test_reupload_as_editor_or_admin_succeeds():
    for role in ("editor", "admin"):
        repo = MagicMock()
        repo.get.return_value = {
            "id": "doc-1",
            "tenant_id": "tenant_a",
            "file_name": "a.pdf",
            "file_content_hash": "old-hash",
            "classification_status": "auto_labeled",
        }
        _as_user(role=role, tenant_id="tenant_a")

        with (
            patch(f"{_MODULE}.DocumentsRepository", return_value=repo),
            patch(f"{_MODULE}.ChunksRepository") as MockChunksRepo,
            patch(f"{_MODULE}.on_file_reupload") as mock_on_reupload,
            patch.object(BackgroundTasks, "add_task") as mock_add_task,
        ):
            resp = client.post(
                "/api/documents/doc-1/reupload",
                files={"file": ("a.pdf", b"new content", "application/pdf")},
            )

        assert resp.status_code == 200, f"role={role} 應允許 reupload"
        assert resp.json() == {"document_id": "doc-1", "processing_status": "parsing"}
        mock_on_reupload.assert_called_once_with("doc-1", b"new content", documents_repo=repo)
        repo.update_for_reupload.assert_called_once()
        args, kwargs = repo.update_for_reupload.call_args
        assert args[0] == "doc-1"
        assert args[2] == "parsing"
        MockChunksRepo.return_value.delete_by_document.assert_called_once_with("doc-1")
        mock_add_task.assert_called_once()
        add_task_args, add_task_kwargs = mock_add_task.call_args
        assert add_task_args[0] is documents.process_pdf_document
        assert add_task_kwargs == {
            "document_id": "doc-1",
            "tenant_id": "tenant_a",
            "file_bytes": b"new content",
            "file_name": "a.pdf",
        }


def test_reupload_as_viewer_returns_403():
    _as_user(role="viewer")

    with (
        patch(f"{_MODULE}.DocumentsRepository") as MockRepo,
        patch(f"{_MODULE}.ChunksRepository") as MockChunksRepo,
        patch.object(BackgroundTasks, "add_task") as mock_add_task,
    ):
        resp = client.post(
            "/api/documents/doc-1/reupload",
            files={"file": ("a.pdf", b"new content", "application/pdf")},
        )

    assert resp.status_code == 403
    MockRepo.return_value.update_for_reupload.assert_not_called()
    MockChunksRepo.return_value.delete_by_document.assert_not_called()
    mock_add_task.assert_not_called()


def test_reupload_missing_document_returns_404():
    repo = MagicMock()
    repo.get.return_value = None
    _as_user(role="editor", tenant_id="tenant_a")

    with patch(f"{_MODULE}.DocumentsRepository", return_value=repo):
        resp = client.post(
            "/api/documents/missing/reupload",
            files={"file": ("a.pdf", b"new content", "application/pdf")},
        )

    assert resp.status_code == 404


def test_reupload_cross_tenant_returns_404():
    repo = MagicMock()
    repo.get.return_value = {
        "id": "doc-1",
        "tenant_id": "tenant_b",
        "file_name": "a.pdf",
        "file_content_hash": "old-hash",
        "classification_status": "auto_labeled",
    }
    _as_user(role="editor", tenant_id="tenant_a")

    with patch(f"{_MODULE}.DocumentsRepository", return_value=repo):
        resp = client.post(
            "/api/documents/doc-1/reupload",
            files={"file": ("a.pdf", b"new content", "application/pdf")},
        )

    assert resp.status_code == 404


def test_reupload_flags_for_review_when_locked_and_hash_changed():
    """spec §4.3：hash 有變且原本已鎖定時觸發 flag_for_review，不自動解鎖
    （classification_status 不應被 reupload 端點動到）。"""
    repo = MagicMock()
    repo.get.return_value = {
        "id": "doc-1",
        "tenant_id": "tenant_a",
        "file_name": "a.pdf",
        "file_content_hash": hashlib.sha256(b"old content").hexdigest(),
        "classification_status": "manually_verified",
    }
    _as_user(role="editor", tenant_id="tenant_a")

    with (
        patch(f"{_MODULE}.DocumentsRepository", return_value=repo),
        patch(f"{_MODULE}.ChunksRepository"),
        patch("app.services.classification.flag_for_review") as mock_flag,
        patch.object(BackgroundTasks, "add_task"),
    ):
        resp = client.post(
            "/api/documents/doc-1/reupload",
            files={"file": ("a.pdf", b"new content", "application/pdf")},
        )

    assert resp.status_code == 200
    mock_flag.assert_called_once_with("doc-1")
    repo.reorganize.assert_not_called()


def test_reupload_rejects_unsupported_content_type_returns_422():
    _as_user(role="editor", tenant_id="tenant_a")

    with (
        patch(f"{_MODULE}.DocumentsRepository") as MockRepo,
        patch.object(BackgroundTasks, "add_task") as mock_add_task,
    ):
        resp = client.post(
            "/api/documents/doc-1/reupload",
            files={
                "file": (
                    "a.docx",
                    b"fake docx bytes",
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            },
        )

    assert resp.status_code == 422
    MockRepo.return_value.get.assert_not_called()
    mock_add_task.assert_not_called()


def test_delete_document_as_viewer_returns_403():
    """spec §3.2：Viewer 無權上傳/修改/刪除，比照 reorganize 的 require_role 寫法。"""
    _as_user(role="viewer")

    with patch(f"{_MODULE}.DocumentsRepository") as MockRepo:
        resp = client.delete("/api/documents/doc-1")

    assert resp.status_code == 403
    MockRepo.return_value.delete.assert_not_called()


def test_delete_document_as_editor_or_admin_succeeds():
    for role in ("editor", "admin"):
        repo = MagicMock()
        repo.delete.return_value = {"id": "doc-1"}
        _as_user(role=role, tenant_id="tenant_a")

        with patch(f"{_MODULE}.DocumentsRepository", return_value=repo):
            resp = client.delete("/api/documents/doc-1")

        assert resp.status_code == 200, f"role={role} 應允許刪除"
        assert resp.json() == {"document_id": "doc-1"}
        repo.delete.assert_called_once_with("doc-1", tenant_id="tenant_a")


def test_delete_document_cross_tenant_returns_404():
    """DocumentsRepository.delete() 的 WHERE 條件直接帶 tenant_id（見該方法註解：
    repositories 用 service_role bypass RLS），跨租戶刪除等同 0 筆命中，回傳 None。
    """
    repo = MagicMock()
    repo.delete.return_value = None
    _as_user(role="editor", tenant_id="tenant_a")

    with patch(f"{_MODULE}.DocumentsRepository", return_value=repo):
        resp = client.delete("/api/documents/doc-1")

    assert resp.status_code == 404
    repo.delete.assert_called_once_with("doc-1", tenant_id="tenant_a")


def test_delete_document_missing_returns_404():
    repo = MagicMock()
    repo.delete.return_value = None
    _as_user(role="admin", tenant_id="tenant_a")

    with patch(f"{_MODULE}.DocumentsRepository", return_value=repo):
        resp = client.delete("/api/documents/missing")

    assert resp.status_code == 404


def test_delete_document_without_authorization_header_returns_422():
    resp = client.delete("/api/documents/doc-1")

    assert resp.status_code == 422


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
    repo.reorganize.assert_called_once_with("doc-1", ["2026核心資料"], tenant_id="tenant_a")


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


def test_reorganize_cross_tenant_returns_404():
    """DocumentsRepository.reorganize() 的 WHERE 條件直接帶 tenant_id（比照 delete()），
    跨租戶等同 0 筆命中，回傳 None，和「文件不存在」一律回 404，不特別區分。
    """
    repo = MagicMock()
    repo.reorganize.return_value = None
    _as_user(role="editor", tenant_id="tenant_a")

    with patch(f"{_MODULE}.DocumentsRepository", return_value=repo):
        resp = client.post(
            "/api/documents/reorganize",
            json={"document_id": "doc-1", "manual_categories": ["財務"]},
        )

    assert resp.status_code == 404
    repo.reorganize.assert_called_once_with("doc-1", ["財務"], tenant_id="tenant_a")


def test_unlock_as_admin_succeeds():
    repo = MagicMock()
    repo.unlock_bulk.return_value = [{"id": "doc-1"}, {"id": "doc-2"}]
    _as_user(role="admin", tenant_id="tenant_a")

    with patch(f"{_MODULE}.DocumentsRepository", return_value=repo):
        resp = client.post(
            "/api/documents/unlock",
            json={"document_ids": ["doc-1", "doc-2"]},
        )

    assert resp.status_code == 200
    assert resp.json()["unlocked_document_ids"] == ["doc-1", "doc-2"]
    repo.unlock_bulk.assert_called_once_with(["doc-1", "doc-2"], tenant_id="tenant_a")


def test_unlock_excludes_cross_tenant_document_ids():
    """跨租戶的 document_id 會被 WHERE 條件過濾掉、不影響任何列（比照 delete()/reorganize()），
    與既有「僅對已鎖定文件生效」的部分成功語意一致，不需要另外回錯誤。
    """
    repo = MagicMock()
    repo.unlock_bulk.return_value = [{"id": "doc-1"}]
    _as_user(role="admin", tenant_id="tenant_a")

    with patch(f"{_MODULE}.DocumentsRepository", return_value=repo):
        resp = client.post(
            "/api/documents/unlock",
            json={"document_ids": ["doc-1", "doc-in-tenant-b"]},
        )

    assert resp.status_code == 200
    assert resp.json()["unlocked_document_ids"] == ["doc-1"]
    repo.unlock_bulk.assert_called_once_with(["doc-1", "doc-in-tenant-b"], tenant_id="tenant_a")


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
