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

    def get_by_content_hash(self, file_content_hash: str, tenant_id: str) -> dict | None:
        """上傳前查重複用（見 upload_document）：同租戶內內容 hash 完全相同即視為重複，
        不比檔名。`tenant_id` 帶進 WHERE 條件的理由同 `delete()`/`reorganize()`。
        """
        resp = (
            self._client.table("documents")
            .select("*")
            .eq("tenant_id", tenant_id)
            .eq("file_content_hash", file_content_hash)
            .limit(1)
            .execute()
        )
        return resp.data[0] if resp.data else None

    def get_by_file_name(self, file_name: str, tenant_id: str) -> dict | None:
        """上傳前查檔名碰撞用（見 upload_document）：檔名相同、內容 hash 不同時，
        不能自動判斷是版本更新還是同名的不同文件，交由使用者在前端選擇。
        """
        resp = (
            self._client.table("documents")
            .select("*")
            .eq("tenant_id", tenant_id)
            .eq("file_name", file_name)
            .limit(1)
            .execute()
        )
        return resp.data[0] if resp.data else None

    def update_for_reupload(self, document_id: str, file_content_hash: str, processing_status: str) -> None:
        """使用者明確選擇「覆蓋既有文件」時呼叫（見 reupload_document 端點）：更新
        file_content_hash 並重置 processing_status，讓 pipeline 重新跑一次。刻意不動
        classification_status——內容變更是否需要 flag_for_review 由呼叫端另外呼叫
        `services/classification.on_file_reupload` 判斷（見 spec §4.3），這裡不重複邏輯。
        """
        self._client.table("documents").update(
            {
                "file_content_hash": file_content_hash,
                "processing_status": processing_status,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        ).eq("id", document_id).execute()

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

    def apply_auto_classification(self, document_id: str, auto_categories: list[str], tenant_id: str) -> dict | None:
        """auto_classify 成功時呼叫（見 services/classification.py）：寫入 auto_categories，
        final_categories 此時尚無人工整理、以 auto 為準，狀態鎖從 pending_auto 推進為 auto_labeled。

        `.neq("classification_status", "manually_verified")` 直接寫進 WHERE（見 spec §4.2 硬性
        要求），一次 UPDATE 完成條件判斷與寫入，避免「先 get 再 update」在背景任務併發時的
        race condition；已鎖定的文件此呼叫不會有任何列被更新，回傳 None。
        """
        resp = (
            self._client.table("documents")
            .update(
                {
                    "auto_categories": auto_categories,
                    "final_categories": auto_categories,
                    "classification_status": "auto_labeled",
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            .eq("id", document_id)
            .eq("tenant_id", tenant_id)
            .neq("classification_status", "manually_verified")
            .execute()
        )
        return resp.data[0] if resp.data else None

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
