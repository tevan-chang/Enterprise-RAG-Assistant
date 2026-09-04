# 0002. 背景任務：FastAPI BackgroundTasks（取代 Celery）

## Context

文件上傳後需要跑 `parsing → chunking → embedding` 這條非同步 pipeline，原規劃可能引入 Celery + broker（Redis/RabbitMQ）處理背景任務。但 Celery 需要額外部署獨立的 broker 與 worker 服務，這在「單人開發、2 週時程、Render 單一 Docker Web Service」的部署限制下，是超出可負擔維運能力的基礎設施（見 CLAUDE.md §1 明確禁止「Celery 或任何獨立 broker+worker 架構」）。

FastAPI 原生 `BackgroundTasks` 可以 in-process 方式處理同樣的非同步流程，不需要額外服務，但已知最大弱點是：容器崩潰或重啟會直接造成 Task Loss，任務狀態永遠卡在 `parsing`/`chunking`，前端 Polling 會無限期等待下去。

## Decision

採用 FastAPI `BackgroundTasks` 處理文件解析 pipeline 與 Gmail 通知發送，並針對其 Task Loss 弱點加上防禦機制：

- `POST /api/documents/upload` 用 `background_tasks.add_task(...)` 直接派發解析任務，不引入額外服務
- 前端以 `processing_status` 欄位（`parsing → chunking → embedding → completed/failed`）做短間隔（2 秒）Polling 取得進度，不用 SSE（見 spec §2.3，SSE 只保留給 Chat）
- **Zombie Task Health Check**：在 FastAPI `lifespan` 啟動階段跑一次（`services/zombie_cleanup.py`），掃描 `processing_status` 仍卡在 `parsing`/`chunking`/`embedding` 且 `updated_at` 超過門檻（10 分鐘）的紀錄，直接標記 `failed`，避免前端無限期 Polling。刻意設計成「啟動時跑一次」而非常駐輪詢，因為 Zombie 只會在容器重啟後才需要被清理，不需要持續背景掃描
- 升級路徑：明確只在「實測吞吐量瓶頸出現時」才考慮升級 Celery，不可預先實作（見 spec §2.1）

## Consequences

**取得的好處**：
- 不需要部署與維運額外的 broker/worker 服務，符合單人開發時程與 Render 單一容器的部署現實
- Zombie Task Health Check 把 Celery 相對於 BackgroundTasks 的核心弱點（Task Loss）用最小成本補上，論述上站得住腳
- Task 邏輯（`cleanup_zombie_tasks`、pipeline 函式）都寫成 pure function，未來真要升級 Celery，也只是替換派發層，不需重寫業務邏輯

**付出的代價**：
- 相較 Celery，沒有內建 retry/backoff 機制，任務失敗（非崩潰情境）需要靠 pipeline 自身的 try/except 處理，不會自動重試
- Zombie 偵測有偵測延遲（最長 10 分鐘門檻期間內使用者仍在等待），不是即時感知容器崩潰
- 無法做到跨多執行個體的任務分派與負載平衡，僅適合目前單一 Render Web Service 的部署規模
