from datetime import datetime, timedelta, timezone

from app.db import get_supabase_client

_ZOMBIE_CANDIDATE_STATUSES = ["parsing", "chunking", "embedding"]


class DocumentsRepository:
    def __init__(self):
        self._client = get_supabase_client()

    def create(self, tenant_id: str, file_name: str) -> dict:
        resp = (
            self._client.table("documents")
            .insert({"tenant_id": tenant_id, "file_name": file_name, "processing_status": "parsing"})
            .execute()
        )
        return resp.data[0]

    def get(self, document_id: str) -> dict | None:
        resp = self._client.table("documents").select("*").eq("id", document_id).limit(1).execute()
        return resp.data[0] if resp.data else None

    def update_status(self, document_id: str, processing_status: str) -> None:
        self._client.table("documents").update(
            {
                "processing_status": processing_status,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        ).eq("id", document_id).execute()

    def find_zombie_tasks(self, timeout_minutes: int) -> list[dict]:
        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=timeout_minutes)).isoformat()
        resp = (
            self._client.table("documents")
            .select("id, file_name, processing_status, updated_at")
            .in_("processing_status", _ZOMBIE_CANDIDATE_STATUSES)
            .lt("updated_at", cutoff)
            .execute()
        )
        return resp.data or []

    def mark_failed_bulk(self, document_ids: list[str]) -> None:
        if not document_ids:
            return
        self._client.table("documents").update({"processing_status": "failed"}).in_(
            "id", document_ids
        ).execute()
