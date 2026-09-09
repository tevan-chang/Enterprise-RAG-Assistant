# 0007. sync-knowledge-base 端點：API Key 驗證 + 複用 zombie cleanup

## Context

Day 9-10 Buffer 新增 `POST /api/v1/admin/sync-knowledge-base`（供外部 GitHub Actions Cron 觸發增量同步）與 `POST /api/v1/admin/test-notification`（Dev/Admin 健檢，測試 Gmail 憑證連線）。這兩個端點都掛在 `routers/admin.py`，但呼叫方性質完全不同：前者是沒有使用者 session 的外部排程服務，後者是已登入的 Admin 從前端/Swagger 手動觸發。`dependencies/auth.py` 目前只有 `get_current_user`/`require_role` 這一種基於 Supabase JWT 的驗證機制，全 repo 沒有任何 API-Key 風格的驗證依賴可以直接套用在 sync 端點上。

另外，`sync-knowledge-base` 的「增量同步」實際要做什麼並不是一個現成問題——規格書 §5 本身把這支端點標註為「架構能力展示」而非核心 Demo 路徑，且系統目前完全沒有外部資料源連接器（文件一律由使用者手動上傳，沒有 Google Drive/S3/任何第三方知識庫可以「同步」）。如果照字面意思做「重新掃描外部來源」，等於要無中生有發明一個假的資料源與掃描邏輯，純粹是為了讓這支端點「看起來有事做」。

## Decision

**驗證機制**：`sync-knowledge-base` 新增 `require_sync_api_key`（`routers/admin.py`），比對 `X-API-Key` header 與 `settings.sync_api_key`（讀自環境變數 `SYNC_API_KEY`），驗證失敗一律 `HTTPException(401, ...)`，寫法比照 `get_current_user` 的「解不出來就 401」風格。`test-notification` 則沿用既有的 `require_role({"admin"})` JWT 驗證。兩個端點在同一個 router 檔案內並存兩種驗證機制，是刻意對應兩種呼叫方（外部排程 vs. 登入使用者），不是不一致。

**同步邏輯**：`services/sync.py::run_incremental_sync()` 不建立任何新的「掃描外部來源」邏輯，直接複用既有 `services/zombie_cleanup.py::cleanup_zombie_tasks()`（原本只在 FastAPI `lifespan` 啟動時跑一次），完成後透過 `send_notification(RAG_SYNC_COMPLETED, ...)` 把清理結果（`zombie_marked_failed` 筆數）通知 Admin。等於把「外部 Cron 主動觸發」當成 zombie cleanup 的第二個觸發時機點，而不是發明一套獨立的同步機制。

## Consequences

**取得的好處**：
- 驗證機制對應呼叫方性質，職責清楚：拿到 `SYNC_API_KEY` 的只有外部 CI/CD 系統，拿不到也不需要登入 session；`test-notification` 則走一般使用者權限模型，不需要額外管理一組獨立的健檢用密鑰。
- `run_incremental_sync()` 沒有任何新的資料源/掃描邏輯需要撰寫或測試，完全複用 `cleanup_zombie_tasks()` 既有的、已經在生產環境驗證過的行為，新增的程式碼量與測試成本都極小，符合 Guardrail「不要為了展示而過度設計」。
- 誠實反映了 `BackgroundTasks` 相對 Celery 的已知弱點（容器崩潰即 Task Loss）：外部 Cron 觸發等於多了一個「不必等下次服務重啟」就能主動清理孤兒任務的管道，這是一個真實存在、值得展示的架構考量，而不是為了填滿端點功能硬湊的情境。

**付出的代價**：
- `sync-knowledge-base` 目前對「知識庫」完全沒有實質同步效果——如果之後真的要接外部資料源（例如 Google Drive 匯入），現在的 `run_incremental_sync()` 需要整個重寫，現有的 zombie cleanup 複用邏輯屆時會變成兩個同步情境（孤兒任務清理 + 外部資料源同步）並存，需要重新設計成兩支獨立的背景任務，不能直接擴充現有函式。
- 全 repo 出現了兩種平行的驗證機制（JWT / API Key），未來如果再新增其他「無使用者 session」的端點，需要留意重複造出第三種驗證慣例；`SYNC_API_KEY` 是單一固定密鑰、沒有過期機制或多組密鑰管理，安全性明顯弱於 JWT，僅適合這種低頻、單一呼叫方（GitHub Actions）的場景，不能直接套用在更高風險的端點上。
