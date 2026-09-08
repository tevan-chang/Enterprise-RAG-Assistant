from unittest.mock import MagicMock, patch

from app.repositories.documents_repository import DocumentsRepository

_MODULE = "app.repositories.documents_repository"


def _repo_with_mock_client() -> tuple[DocumentsRepository, MagicMock]:
    with patch(f"{_MODULE}.get_supabase_client") as mock_get_client:
        client = MagicMock()
        mock_get_client.return_value = client
        repo = DocumentsRepository()
    return repo, client


def test_apply_auto_classification_filters_out_manually_verified_documents():
    """DoD 關鍵斷言（見 spec §4.2）：UPDATE 的 WHERE 條件必須帶
    classification_status != 'manually_verified'，一次 UPDATE 完成條件判斷與寫入，
    避免「先 get 再 update」在背景任務併發時覆蓋人工鎖定的分類結果。
    """
    repo, client = _repo_with_mock_client()
    query = client.table.return_value.update.return_value.eq.return_value.eq.return_value
    query.neq.return_value.execute.return_value = MagicMock(data=[{"id": "doc-1"}])

    result = repo.apply_auto_classification("doc-1", ["財務報表"], "tenant_a")

    query.neq.assert_called_once_with("classification_status", "manually_verified")
    update_payload = client.table.return_value.update.call_args.args[0]
    assert update_payload["auto_categories"] == ["財務報表"]
    assert update_payload["final_categories"] == ["財務報表"]
    assert update_payload["classification_status"] == "auto_labeled"
    assert result == {"id": "doc-1"}


def test_apply_auto_classification_returns_none_when_locked():
    """已鎖定文件命中 .neq 過濾條件，UPDATE 影響 0 列，回傳 None。"""
    repo, client = _repo_with_mock_client()
    query = client.table.return_value.update.return_value.eq.return_value.eq.return_value
    query.neq.return_value.execute.return_value = MagicMock(data=[])

    result = repo.apply_auto_classification("doc-1", ["財務報表"], "tenant_a")

    assert result is None
