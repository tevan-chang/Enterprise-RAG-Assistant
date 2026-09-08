from functools import lru_cache

from openai import APIError, AsyncOpenAI

from app.config import settings
from app.services.token_usage import record_usage


class EmbeddingError(Exception):
    pass


@lru_cache
def _get_client() -> AsyncOpenAI:
    return AsyncOpenAI(api_key=settings.openai_api_key)


async def embed_texts(
    texts: list[str],
    *,
    tenant_id: str | None = None,
    user_id: str | None = None,
) -> list[list[float]]:
    """呼叫 OpenAI text-embedding-3-small，一律 Native SDK（見 CLAUDE.md §1）。

    失敗（含 API Key 未設定、額度不足、逾時等）一律包成 EmbeddingError，
    交由呼叫端（document_pipeline）決定 processing_status 轉 failed（見 spec §2.5）。

    `tenant_id`/`user_id` 皆有值時才記錄 token usage（見 spec §10 Demo 版計費，
    feature="embedding"）：`adapters/retrievers.py` 檢索時呼叫查詢向量化不帶這兩個參數，
    刻意不記錄（單次查詢字串成本可忽略，記錄點集中在文件上傳的 chunk embedding）。
    """
    if not texts:
        return []

    try:
        response = await _get_client().embeddings.create(model=settings.embedding_model, input=texts)
    except APIError as exc:
        raise EmbeddingError(f"embedding 生成失敗: {exc}") from exc

    if tenant_id is not None and user_id is not None:
        record_usage(
            tenant_id=tenant_id,
            user_id=user_id,
            feature="embedding",
            model=settings.embedding_model,
            prompt_tokens=response.usage.prompt_tokens,
            completion_tokens=0,
        )

    return [item.embedding for item in response.data]
