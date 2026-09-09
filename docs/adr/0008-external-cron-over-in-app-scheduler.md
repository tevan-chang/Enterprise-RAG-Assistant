# 0008. 增量同步觸發：外部 Cron（取代應用內 Scheduler）

## Context

`POST /api/v1/admin/sync-knowledge-base`（見 0007-sync-endpoint-api-key-and-zombie-cleanup-reuse.md）需要一個「定期觸發」的機制。直覺選項是在 FastAPI 內掛一個常駐排程器（`APScheduler`、`Celery Beat`），但這會撞上兩個限制：

- CLAUDE.md §2 Guardrail #12 明確禁止應用內常駐 Scheduler：增量同步邏輯一律是外部 Cron 觸發的 API 端點，不在 FastAPI 內常駐排程。
- Render 免費/低階方案的容器會 idle 休眠（見 §16.3「防休眠機制」），常駐 Scheduler 依賴容器持續在跑；容器休眠後排程狀態（下一次觸發時間、是否漏跑）不可靠，休眠又被喚醒時排程器的內部計時器不會自動「補跑」錯過的區間，等於自己要再處理一層「醒來後要不要立刻跑一次」的邊界情況。

## Decision

增量同步一律由外部排程服務（GitHub Actions Cron / Cron-job.org）帶 `X-API-Key` 呼叫 `sync-knowledge-base` 端點觸發，應用程式本身不維護任何排程狀態或計時器。觸發頻率定為**每日 1 次**——增量同步目前實質是複用 `cleanup_zombie_tasks()`（見 0007），屬於低頻率的健檢/清理性質工作，不需要高頻觸發；日後若真的接上外部資料源同步，再依實際資料變動頻率調整 cron 排程，不需要更動應用程式本身。

## Consequences

**取得的好處**：
- 跟 0002-backgroundtasks-over-celery.md（Celery → BackgroundTasks）是同一套取捨邏輯：一人維運下，額外的 Scheduler 程序等於多一個要顧的 moving part（要監控它有沒有活著、要處理容器重啟後排程遺失），不是可負擔的維運成本。
- 排程可靠度與成本比更好：GitHub Actions / Cron-job.org 本身免費、有現成的執行紀錄與監控介面，失敗會留下 Actions log 可回溯，不需要自己刻一套排程系統的失敗告警。
- 不依賴容器保持常駐——容器 idle 休眠時沒有排程器在空轉等待下一次觸發，外部 Cron 呼叫時容器被喚醒即可（配合 §16.3 的防休眠 ping，冷啟動延遲也被緩解）。

**付出的代價**：
- 排程時間精度綁定外部服務的執行間隔與可用性，不在應用程式的控制範圍內；若外部 Cron 服務本身故障或誤刪排程，應用端不會主動感知（沒有「預期應該被呼叫但沒被呼叫」的偵測機制）。
- 觸發時機與應用程式部署是分離的兩份設定（`SYNC_API_KEY` 環境變數 + 外部服務的 cron 設定），新增/變更排程頻率需要到外部服務手動調整，不是單一 repo 內可以 code review 的變更。

## 常見問題與回答依據

- 這條端點不排入 2 分鐘 Demo 劇本（見 spec §13.2），是「架構能力展示」，被問到才展示。
- 預期問題「為什麼不做應用內排程？」→ 見上方 Context/Decision。
- 預期問題「怎麼避免同步時重複處理？」→ 見 0007-sync-endpoint-api-key-and-zombie-cleanup-reuse.md 與 spec §4.3 的 `file_content_hash` 增量判斷邏輯，同步觸發的是既有 pipeline，天生具備幂等性，不需要額外的「已同步過」標記。
- 預期問題「`sync-knowledge-base` 用 GitHub Actions，`/health` 防休眠 ping 卻用 Cron-job.org，為什麼兩個排程用不同服務？」→ 這是 repo 是 **Private** 這個具體限制推出來的取捨，不是隨意選的：GitHub Free 方案 Private repo 只有 2000 分鐘/月 Actions 額度，`/health` 需要 <15 分鐘觸發一次才能防止 Render 免費層 idle 休眠，若選每 10 分鐘（一天 144 次），一個月就要燒 4000+ 分鐘，遠超額度；`sync-knowledge-base` 一天只跑 1 次，一個月才耗約 30 分鐘，額度內完全沒問題，可以留在 repo 內用 GitHub Actions（版本可追蹤、code review 得到）。`/health` 因此改用 Cron-job.org 這個對免費用量沒有月配額限制的外部服務（已查證：官方 FAQ 明講不限制 cronjob 數量、最短間隔可到 1 分鐘、無日/月執行次數上限，只在濫用時保留停權權利），每 10 分鐘 ping 對它而言用量極輕。這題答得出來代表對「免費額度」這種真實維運限制有具體感知，不是紙上談兵。
- 預期問題「怎麼確認這兩個排程真的有在跑，不是紙上談兵？」→ `sync-knowledge-base` 已用 `gh workflow run` 手動觸發驗證成功（GitHub Actions log 可查）；`/health` ping 已在 Cron-job.org 後台看到「Last execution: Successful (985 ms)」的實際執行紀錄，不是只有文件寫「應該要做」。
- 屬於 roadmap Day 9-10（Buffer）任務，跟 Gmail Adapter、Vercel/Render 部署是同批次工作，已於 2026-09-10 完成並驗證。

## 現況（2026-09-10）

後端已部署至 Render（`https://enterprise-rag-backend-43lh.onrender.com`）。

- `/health` 防休眠 ping：**已上線**，Cron-job.org 排程任務「RAG Assistant Backend Health Ping」每 10 分鐘 GET `/health`，已驗證執行成功。
- `sync-knowledge-base` 每日 Cron：`.github/workflows/sync-knowledge-base.yml` 已 merge 進 `master`，`SYNC_API_KEY` GitHub Secret 已設定，並已用 `gh workflow run sync-knowledge-base.yml` 手動觸發驗證成功（job 4 秒完成，回傳 `{"status":"sync_started"}`），每日 UTC 18:00 排程會照此路徑自動執行。
