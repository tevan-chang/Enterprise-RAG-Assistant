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
            }
            for chunk in chunks
        ]
        self._client.table("document_chunks").insert(rows).execute()

    def list_by_document(self, document_id: str) -> list[dict]:
        resp = (
            self._client.table("document_chunks")
            .select("chunk_index, page_number, content, token_count")
            .eq("document_id", document_id)
            .order("chunk_index")
            .execute()
        )
        return resp.data or []
