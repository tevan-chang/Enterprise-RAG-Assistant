# CLAUDE.md — Enterprise AI Knowledge & Report Assistant

> 完整設計理由見 `docs/spec_v3.1.md`。
> 每日任務範圍與 DoD 見 `docs/dev_roadmap_v3.1.md`。
> 本檔只放「每次對話都必須遵守」的穩定規則，不含每日任務細節——那些會隨進度變動，一律去 roadmap 查。

---

## 1. 技術棧速查

| 分類 | 技術 |
| :---- | :---- |
| 後端 | Python 3.11+, FastAPI (async/await), Pydantic **v2**, Uvicorn |
| 資料庫 | PostgreSQL + pgvector（Supabase Local CLI → Supabase Cloud 正式環境） |
| 認證/隔離 | Supabase Auth + JWT + RLS |
| 前端 | Next.js 14（App Router, TypeScript）, Tailwind CSS, Shadcn UI |
| 前端部署 | Vercel |
| 後端部署 | Render（Docker Web Service） |
| AI | OpenAI GPT-4o, text-embedding-3-small — **一律 Native SDK，不引入 LangChain/LlamaIndex/Haystack** |
| 文件解析 | pdfplumber（PDF）, pandas（XLSX）；解析異常一律 fallback 到 LlamaParse |
| 檢索 | pgvector Dense + Metadata Filter + Adapter Pattern（`BaseRetriever`） |
| 通知 | `google-api-python-client`（Gmail API） |
| Observability | Sentry |
| 測試 | pgTAP（DB/RLS）, Pytest（API 合約）, Playwright（僅 1 條 E2E） |
| 部署 | Docker Compose（本地）+ Vercel/Render（正式） |

**架構層級禁用**：Kubernetes / Kafka / Elasticsearch、微服務架構 / Event Sourcing / 複雜 DDD、Celery 或任何獨立 broker+worker、任何以獨立可部署服務形式存在的 reranker、無邊界 Agent loop（多步規劃/reflection/持續 loop）。

---

## 2. Guardrail 強制規則（違反即視為 bug，不是風格建議）

以下每一條都是**強制規則**，非「建議」。生成代碼前後都要對照檢查：

1. 背景任務一律用 `BackgroundTasks`，並在 `lifespan` 啟動階段加入殭屍任務清理（不是常駐輪詢，是啟動時跑一次）。
2. 檢索一律用 `DenseRetriever`（pgvector + Metadata Filter）。**禁止生成任何應用層 `rank_bm25` / 倒排索引邏輯**。RRF 相關程式碼只能以 `RRFFusionRetriever` 的介面/註解形式存在，禁止實作內容。
3. 進度更新一律用 Polling；**SSE 僅限 `/api/query`（Chat）**，禁止在其他端點使用 SSE。
4. 文件解析僅處理 PDF/XLSX。**嚴禁生成 PPTX/DOCX 解析代碼**，其餘格式一律走 LlamaParse fallback 或標記為未來擴充（不順手多做）。
5. Tool-calling 一律 bounded（1-2 輪）。出現多步規劃/reflection/持續 loop 需求，視為超出 MVP 範疇，必須主動否決並提出替代方案，不得實作。
6. RLS/RBAC 驗證一律用 pgTAP（Supabase CLI）。**禁止生成 Python 直連 DB 的測試檔**。
7. E2E 測試僅涵蓋「上傳解析」1 條 Happy Path。**禁止把 Chat/Report Mode/Gmail 通知流程擴充進 Playwright**——這些一律用 Pytest API 合約測試覆蓋。
8. 前端**禁止生成拖拽動畫或複雜 DOM 動態效果**的程式碼；互動一律用下拉選單/按鈕 + `router.refresh()`。
9. **嚴禁引入 LangChain、LlamaIndex、Haystack** 等高階 RAG 框架。Prompting、Chunking、Tool-calling 一律手寫 OpenAI Native SDK。
10. **強制使用 Pydantic v2 語法**（`@field_validator`、`model_config`）。**禁止生成 v1 棄用語法**（`@validator`、`class Config`）。
11. Gmail API 發信一律用 `google-api-python-client`，憑證一律讀環境變數。**嚴禁將憑證 JSON 硬編碼或寫死於 repo 內**。
12. **禁止生成應用內常駐 Scheduler**（如 `APScheduler`）。增量同步邏輯一律是外部 Cron（GitHub Actions）觸發的 API 端點，不在 FastAPI 內常駐排程。
13. 涉及 pgvector / Supabase RLS policy / FastAPI BackgroundTasks edge case / Next.js 14 App Router API / Gmail API scopes 的程式碼，生成前必須先查 Context7（見下節），禁止憑訓練記憶生成版本敏感 API。

---

## 3. Context7 強制查詢時機

生成以下任一類型代碼**之前**，必須先查 Context7 取得當前版本文件，不得僅憑訓練記憶生成：

- pgvector 語法
- Supabase RLS policy
- FastAPI `BackgroundTasks` edge case
- Next.js 14 App Router API
- Gmail API scopes

---

## 4. 目錄結構規範

```
backend/app/
  routers/
  services/
  repositories/
  schemas/
  adapters/
frontend/            # Next.js 14 App Router
supabase/
  migrations/
  tests/              # pgTAP
docs/
  spec_v3.1.md
  dev_roadmap_v3.1.md
  adr/
```

---

## 5. 當前任務範圍

- 每次任務開始前，先讀 `docs/dev_roadmap_v3.1.md` 對應的 Day，確認該 Day 的「任務」「DoD」「Guardrail 檢查」三項。
- 未經使用者明確指示，**不要跳做 roadmap 後續 Day 的功能**。
- 完成任務後，對照該 Day 的 DoD 逐項確認，未達成不算完成。

---

## 6. 回答模式

被問及功能實作時，依序執行：

1. 評估對「系統完整性與工程展示效果」的貢獻
2. 分析實作難度（相對於初階自學背景可負擔的合理複雜度）
3. 提供 Demo 版本方案（對照 spec §10 表格）
4. 直接生成可運行代碼（無偽代碼）
5. 若功能有完整版/簡化版落差，明確標註採用哪個版本及原因
6. 若出現過度設計傾向，主動否決並替代

---

## 7. 若使用者要求違反上述任一條

不要直接照做。依序回應：

1. 指出違反的是本檔第幾條 Guardrail（§2 或 §3）
2. 對照 `docs/spec_v3.1.md` 的對應章節說明原始理由
3. 主動提出符合**當前 roadmap Day 範疇**的替代方案
