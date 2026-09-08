from unittest.mock import AsyncMock, MagicMock, patch

from app.config import settings
from app.services.embeddings import embed_texts

_MODULE = "app.services.embeddings"


def _mock_openai_client(vectors: list[list[float]], prompt_tokens: int = 42) -> MagicMock:
    response = MagicMock()
    response.data = [MagicMock(embedding=vector) for vector in vectors]
    response.usage = MagicMock(prompt_tokens=prompt_tokens)
    client = MagicMock()
    client.embeddings.create = AsyncMock(return_value=response)
    return client


async def test_embed_texts_returns_vectors():
    client = _mock_openai_client([[0.1, 0.2], [0.3, 0.4]])

    with patch(f"{_MODULE}._get_client", return_value=client):
        vectors = await embed_texts(["a", "b"])

    assert vectors == [[0.1, 0.2], [0.3, 0.4]]


async def test_embed_texts_records_usage_when_tenant_and_user_provided():
    client = _mock_openai_client([[0.1, 0.2]], prompt_tokens=99)

    with (
        patch(f"{_MODULE}._get_client", return_value=client),
        patch(f"{_MODULE}.record_usage") as mock_record,
    ):
        await embed_texts(["a"], tenant_id="tenant_a", user_id="user-1")

    mock_record.assert_called_once_with(
        tenant_id="tenant_a",
        user_id="user-1",
        feature="embedding",
        model=settings.embedding_model,
        prompt_tokens=99,
        completion_tokens=0,
    )


async def test_embed_texts_skips_usage_recording_when_tenant_or_user_missing():
    """DenseRetriever 檢索時呼叫查詢向量化不帶 tenant_id/user_id，刻意不記錄用量。"""
    client = _mock_openai_client([[0.1, 0.2]])

    with (
        patch(f"{_MODULE}._get_client", return_value=client),
        patch(f"{_MODULE}.record_usage") as mock_record,
    ):
        await embed_texts(["a"])

    mock_record.assert_not_called()


async def test_embed_texts_returns_empty_list_without_calling_api():
    client = _mock_openai_client([])

    with (
        patch(f"{_MODULE}._get_client", return_value=client),
        patch(f"{_MODULE}.record_usage") as mock_record,
    ):
        vectors = await embed_texts([], tenant_id="tenant_a", user_id="user-1")

    assert vectors == []
    client.embeddings.create.assert_not_called()
    mock_record.assert_not_called()
