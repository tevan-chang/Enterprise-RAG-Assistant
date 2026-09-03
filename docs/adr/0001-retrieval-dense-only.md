# 0001. Retrieval：pgvector Dense-only（取代 Hybrid+RRF）

## Context

企業知識庫檢索原規劃走 Hybrid Search（BM25 + Dense + RRF Fusion）。但 `rank_bm25` 是應用層記憶體內倒排索引，在 FastAPI 多 worker / 服務重啟情境下需要額外處理索引持久化與跨 worker 同步，這項成本在 2 週單人開發時程下不成比例（見 spec §11「應用層 BM25 索引同步/持久化複雜度」風險項）。

另一方面，企業文件多半具備明確的部門歸屬與命名規範，天生適合用結構化欄位先縮小搜尋池，不需要每次都對全庫做關鍵字倒排比對才能達到可用的精準度。

## Decision

檢索架構收斂為「pgvector Dense Search + Metadata Filter」單一路線（路線 B），以 `BaseRetriever` Adapter Pattern 抽象，MVP 僅實作 `DenseRetriever`：

1. 先依 `tenant_id`（必要）、`departments`/`confidentiality`（可選）在 Postgres RPC `match_document_chunks` 內做 Metadata Filter 縮小搜尋池
2. 對縮小後的集合做 pgvector cosine 相似度排序，一次查詢內完成，不在 Python 端事後 `.eq()` 過濾（見 CLAUDE.md 架構總覽「檢索」一節，避免 planner 無法把 filter 跟向量排序一起最佳化）

`RRFFusionRetriever` 依 CLAUDE.md §2 Guardrail #2，僅以 class 簽名 + 介面註解形式保留在 `adapters/retrievers.py`，不實作內容，作為未來若要接 Hybrid Search 的擴充位。

## Consequences

**取得的好處**：
- 不需要維護應用層索引的持久化與多 worker 同步，複雜度完全交給 Postgres/pgvector 原生處理
- Metadata Filter 由 SQL function 內部套用，向量排序與過濾在同一次查詢完成，效能可預期
- Adapter 介面已預留擴充位，未來要接 `RRFFusionRetriever` 不需改動呼叫端（`services/`、`routers/`）

**付出的代價**：
- 純語意檢索在使用者輸入精確關鍵字（如型號、單號）時，召回率可能不如 Hybrid Search，MVP 階段以 Metadata Filter 縮小池部分緩解此弱點，但非完全等價
- `RRFFusionRetriever` 目前只是介面佔位，若未來真的要接 Hybrid Search，仍需要重新評估索引持久化方案（例如改用 Postgres 原生全文檢索 `tsvector` 取代應用層 `rank_bm25`，避免重蹈本決策要避開的同一個坑）
