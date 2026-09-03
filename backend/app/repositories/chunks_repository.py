from app.db import get_supabase_client
from app.services.chunker import Chunk


class ChunksRepository:
    def __init__(self):
        self._client = get_supabase_client()

    def bulk_insert(self, document_id: str, tenant_id: str, chunks: list[Chunk]) -> None:
        if not chunks:
            return
        rows = [
            {
                "document_id": document_id,
                "tenant_id": tenant_id,
                "chunk_index": chunk.chunk_index,
                "page_number": chunk.page_number,
                "content": chunk.content,
                "token_count": chunk.token_count,
                "sheet_name": chunk.sheet_name,
                "cell_range": chunk.cell_range,
                "embedding": chunk.embedding,
            }
            for chunk in chunks
        ]
        self._client.table("document_chunks").insert(rows).execute()

    def list_by_document(self, document_id: str) -> list[dict]:
        resp = (
            self._client.table("document_chunks")
            .select("chunk_index, page_number, content, token_count, sheet_name, cell_range")
            .eq("document_id", document_id)
            .order("chunk_index")
            .execute()
        )
        return resp.data or []

    def match(
        self,
        query_embedding: list[float],
        tenant_id: str,
        top_k: int,
        departments: list[str] | None = None,
        confidentiality: list[str] | None = None,
    ) -> list[dict]:
        """DenseRetriever 用：呼叫 `match_document_chunks` RPC 做 pgvector 語意排序
        （見 supabase/migrations/20260903120000_match_document_chunks_function.sql）。

        Metadata Filter 由 SQL function 內部套用，不在 Python 端事後過濾，
        避免 planner 無法把 filter 跟向量排序一起最佳化。
        """
        resp = self._client.rpc(
            "match_document_chunks",
            {
                "query_embedding": query_embedding,
                "match_tenant_id": tenant_id,
                "match_count": top_k,
                "filter_departments": departments,
                "filter_confidentiality": confidentiality,
            },
        ).execute()
        return resp.data or []
