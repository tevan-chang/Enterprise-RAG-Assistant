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

## 面試防守要點

- 這條端點不排入 2 分鐘 Demo 劇本（見 spec §13.2），是「架構能力展示」，被問到才展示。
- 預期問題「為什麼不做應用內排程？」→ 見上方 Context/Decision。
- 預期問題「怎麼避免同步時重複處理？」→ 見 0007-sync-endpoint-api-key-and-zombie-cleanup-reuse.md 與 spec §4.3 的 `file_content_hash` 增量判斷邏輯，同步觸發的是既有 pipeline，天生具備幂等性，不需要額外的「已同步過」標記。
- 屬於 roadmap Day 9-10（Buffer）任務，跟 Gmail Adapter、Vercel/Render 部署、`/health` 防休眠 ping 是同批次工作。

## 現況（2026-09-10）

後端已部署至 Render（`https://enterprise-rag-backend-43lh.onrender.com`）。

- `/health` 防休眠 ping：**已上線**，Cron-job.org 排程任務「RAG Assistant Backend Health Ping」每 10 分鐘 GET `/health`，已驗證執行成功。
- `sync-knowledge-base` 每日 Cron：`.github/workflows/sync-knowledge-base.yml` 已建立，`schedule: cron` 每日觸發，帶 `X-API-Key` 呼叫正式後端。**需要使用者自行在 repo 設定 `SYNC_API_KEY` GitHub Secret**（值對應 Render 環境變數 `SYNC_API_KEY`）才會真正觸發成功；設定前 workflow 會因 401 失敗，會留下可回溯的 Actions log。
