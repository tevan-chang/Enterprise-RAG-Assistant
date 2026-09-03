from functools import lru_cache

from openai import APIError, AsyncOpenAI

from app.config import settings


class EmbeddingError(Exception):
    pass


@lru_cache
def _get_client() -> AsyncOpenAI:
    return AsyncOpenAI(api_key=settings.openai_api_key)


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """呼叫 OpenAI text-embedding-3-small，一律 Native SDK（見 CLAUDE.md §1）。

    失敗（含 API Key 未設定、額度不足、逾時等）一律包成 EmbeddingError，
    交由呼叫端（document_pipeline）決定 processing_status 轉 failed（見 spec §2.5）。
    """
    if not texts:
        return []

    try:
        response = await _get_client().embeddings.create(model=settings.embedding_model, input=texts)
    except APIError as exc:
        raise EmbeddingError(f"embedding 生成失敗: {exc}") from exc

    return [item.embedding for item in response.data]
