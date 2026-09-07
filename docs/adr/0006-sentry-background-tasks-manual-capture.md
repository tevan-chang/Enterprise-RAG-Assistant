# 0006. Sentry 在 BackgroundTasks 失敗路徑：手動 capture，不靠 middleware 自動涵蓋

## Context

Day 9 要求接 Sentry：「FastAPI exception middleware + BackgroundTasks 失敗捕捉」（見 spec §2.5）。Sentry 官方的 FastAPI/Starlette integration（`StarletteIntegration` + `FastApiIntegration`）是透過 ASGI middleware 攔截「請求—回應週期內」發生的例外，運作機制依賴例外會往上拋到 ASGI app 層級才能被攔截並回報。

但 FastAPI 的 `BackgroundTasks` 是註冊在 response 送出**之後**才執行的 callable，執行時已經脫離原本的 request/response ASGI 呼叫棧；Starlette 內部用 try/except 包住背景任務執行、寫 log 但不會重新往外拋，因此 Sentry 的 ASGI middleware 天生攔不到 `BackgroundTasks` 內部發生的例外——這不是設定沒開對，是這兩種機制的攔截範圍原本就不重疊。

專案裡有四個明確需要被觀測到的 BackgroundTasks／背景邏輯失敗路徑：
- `document_pipeline.py`：PDF/XLSX 解析失敗（含 fallback 失敗）、embedding API 失敗
- `zombie_cleanup.py`：`lifespan` 啟動時把卡死任務標記 `failed`
- `classification.py` 的 `flag_for_review`：文件重傳但分類已鎖定
- `report.py` 的 tool call 執行失敗：雖然已經用結構化錯誤回應給 LLM 繼續組報告（見 ADR 之前的 spec §2.4 錯誤處理設計），但仍需要留 observability 記錄，才能知道實際發生頻率

## Decision

`sentry_sdk.init()`（`backend/app/observability.py` 的 `init_sentry()`）只靠官方 integration 處理一般請求例外，**不寫自訂 exception middleware**。

上述四個失敗路徑，各自在對應的 except 分支或觸發點手動呼叫：
- 有實際例外物件時：`sentry_sdk.capture_exception(exc)`（`document_pipeline.py` 的三個 except 分支）
- 沒有例外、只是業務邏輯認定的失敗/警示事件時：`sentry_sdk.capture_message(..., level="warning")`（`zombie_cleanup.py`、`classification.flag_for_review`、`report.py` 的 tool 錯誤與未知 tool 分支）

未設定 `SENTRY_DSN`（例如本地開發沒申請帳號）時 `init_sentry()` 直接 no-op 跳過；`sentry_sdk` 在未 `init` 的狀態下呼叫 `capture_*` 系列函式本身也是安全的 no-op，所以每個呼叫點都不需要額外判斷「有沒有設定 DSN」。

## Consequences

**取得的好處**：
- 不用為了涵蓋 `BackgroundTasks` 額外寫一層自訂 middleware 或裝飾器抽象，四個失敗路徑各自在既有的 except/失敗判斷分支上加一行呼叫即可，改動量小、容易對照程式碼理解「什麼情況會出現在 Sentry」。
- `capture_message` 與 `capture_exception` 分開使用，讓 Sentry 上能區分「真的丟出例外」跟「業務邏輯認定的失敗事件」，方便之後設定不同的告警規則。
- 不管有沒有設定 DSN 都不需要在呼叫端做防呆判斷，本地開發沒有 Sentry 帳號也不會噴錯或需要額外 mock，四個路徑對應的 pytest（`test_document_pipeline.py`、`test_zombie_cleanup.py`、`test_classification.py`、`test_report_service.py`）都是直接 `patch(f"{_MODULE}.sentry_sdk")` 斷言呼叫，不需要真的連線 Sentry。

**付出的代價**：
- 每次未來新增一個背景失敗路徑，都要記得手動加 capture 呼叫，沒有像請求層 middleware 那樣「自動涵蓋全部」的保障，是需要靠 code review 把關的手動慣例，不是架構性保證。
- `capture_message` 目前訊息內容是手寫字串組出來的（例如 `f"compute_table_metric 失敗: args={args} result={result}"`），沒有用 `tags`/`extra` 傳結構化資訊，Sentry 上用 issue title 分組會比較粗略；之後如果要做更精細的告警分類（例如依 `tenant_id`／`document_id` 篩選），需要重構成用 `capture_message(..., extras=..., tags=...)` 傳結構化 context。
