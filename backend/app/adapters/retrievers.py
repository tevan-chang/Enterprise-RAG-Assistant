from abc import ABC, abstractmethod

from app.config import settings
from app.repositories.chunks_repository import ChunksRepository
from app.services.embeddings import embed_texts

# Viewer 檢索/Citation 存取時自動排除 restricted 機密等級（見 spec §3.3）；
# Admin/Editor 不受此限制。documents router 的 citation 端點也重用此常數（見 roadmap Day 7）。
VIEWER_ALLOWED_CONFIDENTIALITY = ["public", "internal"]


class BaseRetriever(ABC):
    @abstractmethod
    async def retrieve(self, query: str, tenant_id: str, top_k: int = 5) -> list[dict]:
        """回傳依語意相似度排序的 chunk 列表（見 spec §2.2）"""


class DenseRetriever(BaseRetriever):
    """MVP 唯一實作：Supabase pgvector + Metadata Filter（見 spec §2.2 / roadmap Day 5）。

    Metadata Filter 由 `match_document_chunks` SQL function 內部套用（tenant_id 必要，
    departments/confidentiality 可選），縮小搜尋池後再做 pgvector 語意相似度排序。
    """

    def __init__(self, chunks_repo: ChunksRepository | None = None):
        self._chunks_repo = chunks_repo or ChunksRepository()

    async def retrieve(
        self,
        query: str,
        tenant_id: str,
        top_k: int = 5,
        departments: list[str] | None = None,
        role: str = "admin",
    ) -> list[dict]:
        confidentiality = VIEWER_ALLOWED_CONFIDENTIALITY if role == "viewer" else None

        [query_embedding] = await embed_texts([query])
        return self._chunks_repo.match(
            query_embedding=query_embedding,
            tenant_id=tenant_id,
            top_k=top_k or settings.retrieval_top_k,
            departments=departments,
            confidentiality=confidentiality,
        )


# 未來擴充位（不在 MVP 範疇內實作，見 CLAUDE.md §2 Guardrail #2 / spec §2.2）：
# class RRFFusionRetriever(BaseRetriever):
#     """Dense + BM25 的 RRF (Reciprocal Rank Fusion) 融合排序，僅留介面位置，不實作內容。"""
#     async def retrieve(self, query: str, tenant_id: str, top_k: int = 5) -> list[dict]:
#         ...
