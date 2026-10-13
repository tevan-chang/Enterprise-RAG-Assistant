# 0012. 文件列表／上傳 Modal 輪詢同時追蹤 processing_status 與 classification_status，並各自加逾時保護

## Context

`documents.processing_status` 狀態機（`parsing → chunking → embedding → completed/failed`）與 `documents.classification_status` 狀態機（`pending_auto → auto_labeled → manually_verified`）是兩條獨立的非同步流程：`services/document_pipeline.py` 的 `_embed_and_store_chunks` 先把 `processing_status` 寫成 `completed`，才呼叫 `services/classification.py` 的 `auto_classify()`。也就是說，`processing_status === "completed"` 的當下，分類很可能還沒開始或還在跑。

既有的前端輪詢（`app/(dashboard)/documents/page.tsx` 的文件列表、`upload-document-modal.tsx` 的上傳進度）只看 `processing_status` 是否落在 terminal state（`completed`/`failed`）就停止輪詢。這造成兩個問題：

1. 上傳 modal 一看到 `completed` 就顯示成功、停止輪詢，但此時分類可能還在跑甚至尚未觸發，使用者在文件列表看到的分類欄位是空的，體感上像是「漏資料」。
2. `auto_classify()` 失敗（LLM 呼叫或 JSON 解析失敗）時只 log + Sentry，不影響 `processing_status`，但也刻意不重試、不改變 `classification_status`——文件會永遠卡在 `pending_auto`（見 `services/classification.py` docstring）。如果輪詢條件改成「兩個狀態都要收斂」，沒有逾時保護的話，分類永久失敗的文件會讓畫面無限輪詢下去。

## Decision

輪詢判斷改成「`processing_status` 為 `failed`，或 `processing_status === "completed"` 且 `classification_status !== "pending_auto"`」才算完全收斂（`lib/document-status.ts` 的 `isDocumentFullyResolved()`），兩處輪詢共用這個判斷式，但各自加上獨立的逾時保護，逾時後一律當作「已收斂」處理、停止輪詢：

- **文件列表頁**（`app/(dashboard)/documents/page.tsx`）：`refetchInterval` 用 `updated_at` 距今是否超過 `DOCUMENT_POLL_STALL_MS`（10 分鐘，與後端 `zombie_task_timeout_minutes` 預設值同量級）判斷要不要繼續輪詢整頁列表。選這個時間量級是因為 `processing_status` 卡住的 zombie 任務本身就是靠這個 timeout 被 `lifespan` 啟動時的清理機制標記 `failed`，分類卡住沒有對應的清理機制，但沿用同一個量級的逾時值，不另外發明一套時間常數。
- **上傳 Modal**（`upload-document-modal.tsx`）：用 `classificationWaitTicksRef` 累計「`processing_status === "completed"` 且 `classification_status === "pending_auto"`」的輪詢次數，達到 `CLASSIFICATION_MAX_WAIT_TICKS`（10 次 × 2 秒 = 20 秒）就設 `classificationTimedOut = true`、停止輪詢、UI 顯示為完成。分類本身只是一次 LLM 呼叫，正常應在數秒內跑完，20 秒已經是寬裕值；用獨立的 tick 計數器而非 `updated_at`，是因為 modal 情境是「剛上傳的單一文件」，不需要跟列表頁共用 10 分鐘這種保守量級，使用者會直接盯著 modal 等，逾時應該更短。

`GET /{document_id}` 的 `DocumentStatusResponse`（`schemas/documents.py`）新增 `classification_status` 欄位，是這個決策能成立的前提——沒有這個欄位，前端拿不到分類是否完成的資訊。

## Consequences

**取得的好處**：
- 上傳 modal 顯示「完成」時，使用者在文件列表看到的分類欄位已經有值（或已確定逾時放棄），不會再有「上傳顯示成功但分類還是空的」的體感落差。
- 兩個 terminal state 判斷收斂成 `isDocumentFullyResolved()` 一個共用函式，避免文件列表與上傳 modal 各自維護一份邏輯、未來改動只需要改一處。
- 不需要改動後端分類重試邏輯或新增分類專屬的 zombie cleanup，純前端輪詢層面解決「使用者體感等待」問題，符合 Guardrail #3（非 Chat 端點禁止 SSE，一律 Polling）與目前 MVP 範疇。

**付出的代價**：
- 兩處逾時值（10 分鐘 vs 20 秒）是刻意選擇但彼此獨立的 magic number，沒有共用常數或設定值，未來如果要調整其中一個時間量級，不會自動連動到另一個，需要兩處都檢查。
- 分類逾時後 UI 直接當作「已收斂」顯示完成，不會另外標示「分類逾時／失敗」给使用者——如果使用者沒有重新整理頁面去看文件列表的分類欄位，不會知道分類其實沒有成功，這是刻意的簡化（避免在 Demo 版多開一種錯誤狀態 UI），但損失了「分類失敗」這個資訊的能見度。
- `updated_at` 作為文件列表逾時判斷依據，任何更新該文件 row 的操作（包含使用者手動 `reorganize`）都會把它重置，理論上可能讓一個分類卡住很久的文件因為中途被使用者操作過而重新進入輪詢視窗；目前判斷為可接受，因為會觸發 `updated_at` 變動的操作本身就代表文件還有人在互動，繼續輪詢是合理行為。
