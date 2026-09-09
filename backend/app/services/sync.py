from app.services.notifications import RAG_SYNC_COMPLETED, send_notification
from app.services.zombie_cleanup import cleanup_zombie_tasks


async def run_incremental_sync() -> dict:
    """POST /api/v1/admin/sync-knowledge-base 背景執行（見 spec §5）。

    規格書明確標註這支端點屬於「架構能力展示」而非核心 Demo 路徑，且本系統沒有任何
    外部資料源連接器（文件一律由使用者手動上傳）。與其為了展示而發明一套沒有真實
    資料源的假同步邏輯，這裡直接複用既有 services/zombie_cleanup.cleanup_zombie_tasks()
    （原本只在 lifespan 啟動時跑一次）：外部 Cron 觸發等於多了一個「主動清理孤兒任務」
    的管道，是誠實反映 BackgroundTasks 模式下容器重啟風險的架構呈現，而非新增未經
    驗證的複雜邏輯。
    """
    zombie_count = cleanup_zombie_tasks()
    summary = {"zombie_marked_failed": zombie_count}
    await send_notification(RAG_SYNC_COMPLETED, summary)
    return summary
