from unittest.mock import AsyncMock, MagicMock, patch

from app.adapters.retrievers import DenseRetriever

_MODULE = "app.adapters.retrievers"


async def test_dense_retriever_admin_role_has_no_confidentiality_filter():
    chunks_repo = MagicMock()
    chunks_repo.match.return_value = [{"chunk_id": "c1", "content": "hit", "similarity": 0.9}]

    with patch(f"{_MODULE}.embed_texts", new=AsyncMock(return_value=[[0.1, 0.2, 0.3]])):
        results = await DenseRetriever(chunks_repo).retrieve(
            query="測試查詢", tenant_id="tenant_a", top_k=5, role="admin"
        )

    assert results == [{"chunk_id": "c1", "content": "hit", "similarity": 0.9}]
    chunks_repo.match.assert_called_once_with(
        query_embedding=[0.1, 0.2, 0.3],
        tenant_id="tenant_a",
        top_k=5,
        departments=None,
        confidentiality=None,
    )


async def test_dense_retriever_viewer_role_excludes_restricted():
    chunks_repo = MagicMock()
    chunks_repo.match.return_value = []

    with patch(f"{_MODULE}.embed_texts", new=AsyncMock(return_value=[[0.1, 0.2, 0.3]])):
        await DenseRetriever(chunks_repo).retrieve(
            query="測試查詢", tenant_id="tenant_a", top_k=3, role="viewer"
        )

    _, kwargs = chunks_repo.match.call_args
    assert kwargs["confidentiality"] == ["public", "internal"]


async def test_dense_retriever_passes_department_metadata_filter():
    chunks_repo = MagicMock()
    chunks_repo.match.return_value = []

    with patch(f"{_MODULE}.embed_texts", new=AsyncMock(return_value=[[0.1, 0.2, 0.3]])):
        await DenseRetriever(chunks_repo).retrieve(
            query="測試查詢", tenant_id="tenant_a", departments=["財務部"], role="editor"
        )

    _, kwargs = chunks_repo.match.call_args
    assert kwargs["departments"] == ["財務部"]
    assert kwargs["confidentiality"] is None
