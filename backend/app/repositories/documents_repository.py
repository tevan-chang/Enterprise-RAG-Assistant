from datetime import datetime, timedelta, timezone

from app.db import get_supabase_client

_ZOMBIE_CANDIDATE_STATUSES = ["parsing", "chunking", "embedding"]


class DocumentsRepository:
    def __init__(self):
        self._client = get_supabase_client()

    def create(self, tenant_id: str, file_name: str, file_content_hash: str | None = None) -> dict:
        row = {"tenant_id": tenant_id, "file_name": file_name, "processing_status": "parsing"}
        if file_content_hash is not None:
            row["file_content_hash"] = file_content_hash
        resp = self._client.table("documents").insert(row).execute()
        return resp.data[0]

    def get(self, document_id: str) -> dict | None:
        resp = self._client.table("documents").select("*").eq("id", document_id).limit(1).execute()
        return resp.data[0] if resp.data else None

    def list_by_tenant(self, tenant_id: str) -> list[dict]:
        resp = (
            self._client.table("documents")
            .select("*")
            .eq("tenant_id", tenant_id)
            .order("created_at", desc=True)
            .execute()
        )
        return resp.data or []

    def update_status(self, document_id: str, processing_status: str) -> None:
        self._client.table("documents").update(
            {
                "processing_status": processing_status,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        ).eq("id", document_id).execute()

    def update_xlsx_sheets(self, document_id: str, xlsx_sheets: dict) -> None:
        """XLSX 解析成功時存結構化表格資料（見 roadmap Day 8 Schema-First Strategy），
        供 Report Mode 的 `compute_table_metric` 還原 DataFrame 做精確運算用。
        """
        self._client.table("documents").update({"xlsx_sheets": xlsx_sheets}).eq("id", document_id).execute()

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

    def reorganize(self, document_id: str, manual_categories: list[str], tenant_id: str) -> dict | None:
        """手動整理：寫入 manual_categories，final_categories 以人工結果為準，
        狀態鎖升級為 manually_verified（見 spec §4.2 雙軌分類鎖機制）。

        `tenant_id` 直接帶進 WHERE 條件（比照 `delete()`），因為本 client 用 service_role
        key bypass RLS，不能只靠 DB 擋跨租戶操作（見 CLAUDE.md 雙層權限隔離）。
        """
        resp = (
            self._client.table("documents")
            .update(
                {
                    "manual_categories": manual_categories,
                    "final_categories": manual_categories,
                    "classification_status": "manually_verified",
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            .eq("id", document_id)
            .eq("tenant_id", tenant_id)
            .execute()
        )
        return resp.data[0] if resp.data else None

    def delete(self, document_id: str, tenant_id: str) -> dict | None:
        """刪除文件（見 spec §10 端點定義：刪除檔案並觸發向量 Cascade 清理）。

        `tenant_id` 直接帶進 DELETE 的 WHERE 條件，因為本 client 用 service_role key
        bypass RLS（見 app/db.py），不能只靠 DB RLS 擋跨租戶操作（見 CLAUDE.md 雙層權限
        隔離）；`document_chunks` 對應的向量透過既有 FK `on delete cascade` 自動清除，
        不需要額外程式碼。
        """
        resp = (
            self._client.table("documents")
            .delete()
            .eq("id", document_id)
            .eq("tenant_id", tenant_id)
            .execute()
        )
        return resp.data[0] if resp.data else None

    def unlock_bulk(self, document_ids: list[str], tenant_id: str) -> list[dict]:
        """批次解鎖：僅對目前已鎖定（manually_verified）的文件生效，狀態鎖降級為
        auto_labeled，讓背景自動分類排程可以重新覆蓋（見 spec §4.2）。

        `tenant_id` 直接帶進 WHERE 條件（比照 `delete()`），跨租戶的 document_id 會被
        過濾掉、不影響任何列，因為本 client 用 service_role key bypass RLS，不能只靠
        DB 擋跨租戶操作（見 CLAUDE.md 雙層權限隔離）。
        """
        if not document_ids:
            return []
        resp = (
            self._client.table("documents")
            .update(
                {
                    "classification_status": "auto_labeled",
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            .in_("id", document_ids)
            .eq("tenant_id", tenant_id)
            .eq("classification_status", "manually_verified")
            .execute()
        )
        return resp.data or []
