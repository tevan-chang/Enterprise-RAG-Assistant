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
  dependencies/       # 跨 router 共用的 FastAPI 依賴（如 auth.py 的 get_current_user/require_role）
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

## 5.1 每日收尾檢查清單

- [ ] 今天的 code 有沒有出現本檔 §2/§3 明確禁止的模式（BM25 邏輯、DOCX/PPTX 解析、SSE 用在非 Chat 端點、Playwright 覆蓋到 Chat/Report/Gmail、應用內常駐 Scheduler、Gmail 憑證硬編碼、Pydantic v1 語法）
- [ ] 涉及 pgvector/RLS/BackgroundTasks/Next.js App Router/Gmail API 的程式碼，生成前有沒有先查 Context7
- [ ] 今天的架構決策是否值得寫一篇 ADR
- [ ] 今天寫的 code 能不能在面試中用一句話講清楚「為什麼這樣做」

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

---

## 8. 開發指令

**Backend**（於 `backend/` 目錄下執行）：

```bash
pip install -r requirements.txt

pytest                                                    # 跑全部測試
pytest tests/test_document_pipeline.py                    # 跑單一檔案
pytest tests/test_document_pipeline.py::test_process_pdf_document_triggers_fallback_on_parsing_error  # 跑單一測試

uvicorn app.main:app --reload                              # 本地啟動 API
```

- `pytest.ini` 已設 `pythonpath = .` 與 `asyncio_mode = auto`，async test 不需額外裝飾。
- 設定讀取來自 **`backend/.env`**（`app/config.py` 的 `SettingsConfigDict(env_file=".env")` 是相對 cwd），跟 repo 根目錄的 `.env` 是兩個獨立檔案，兩邊都要顧到（根目錄 `.env` 目前存放的是 Supabase Cloud/Gmail 等正式環境憑證）。
- `tests/test_llamaparse_fallback_live.py` 會打真實 LlamaParse API，只有設定 `LLAMA_CLOUD_API_KEY` 時才會執行，否則自動 skip（`pytestmark = pytest.mark.skipif(...)`）。

**Supabase**（於 repo 根目錄執行）：

```bash
supabase start                    # 啟動本地 stack（Postgres/Auth/Storage...）
supabase status                   # 看本地服務網址與金鑰
supabase migration up --local     # 把新 migration 套用到本地 DB
supabase test db                  # 跑 pgTAP（supabase/tests/*.test.sql）
supabase migration list           # 比對本地 vs 遠端 migration 差異
supabase db push --dry-run        # 預覽會推到遠端 Supabase Cloud 的 SQL（先看再決定）
supabase db push                  # 正式套用到遠端（會改動雲端 schema，執行前務必先 dry-run 確認）
```

**CI**：`.github/workflows/ci.yml` 目前只有 `pgtap` 一個 stage（見 roadmap Day 2 DoD：CI 骨架先跑通這一階段），Pytest/Playwright stage 待對應 Day 完成後補上。

**Frontend**（於 `frontend/` 目錄下執行；Day 5 起已串接文件上傳/列表頁）：

```bash
npm install
npm run dev      # 本地啟動（預設 http://localhost:3000）
npm run lint     # next lint
npm run build    # 正式建置
```

- 設定讀取來自 `frontend/.env.local`（`NEXT_PUBLIC_API_BASE_URL`、`NEXT_PUBLIC_SUPABASE_URL`、`NEXT_PUBLIC_SUPABASE_ANON_KEY`，見 `lib/api.ts` / `lib/supabase/client.ts`）。
- 登入走 `app/login/page.tsx`（Supabase Auth email/password + Shadcn Form），`middleware.ts` 用 `@supabase/ssr` 的 `createServerClient` 檢查 session，未登入一律導向 `/login`。`lib/auth-context.tsx` 的 `AuthProvider`/`useAuth()` 取代舊的 `dev-identity.tsx`，暴露 `session`/`user`/`tenantId`/`role`（後兩者從 JWT `app_metadata` 解出，純 UX 遮罩用）；`lib/api.ts` 的 `request()` 一律帶 `Authorization: Bearer <session.access_token>` 打後端，不再用 `X-Tenant-Id`/`X-User-Role` header（見 roadmap Day 7.5）。

**Docker Compose**：尚未實作。`docker-compose.yml` 是 skeleton，兩個 service 都用 `profiles: ["not-yet-implemented"]` 佔位，實際定義排在 roadmap Day 10。

---

## 9. 架構總覽（跨檔案資料流）

**分層**：`routers/`（FastAPI 端點，含 RBAC/驗證）→ `services/`（業務邏輯與 pipeline）→ `repositories/`（Supabase table 存取）與 `adapters/`（外部服務或可替換策略，如 `LlamaParseAdapter`、`DenseRetriever`）→ `schemas/`（Pydantic request/response）。`repositories/` 一律透過 `app/db.py` 的 `get_supabase_client()` 用 **service_role key** 連線（bypass RLS），因此 role-based/confidentiality 過濾**必須**在 Python 層做，不能假設 DB 會擋（見下方雙層權限隔離）。

**文件上傳解析管線**（`services/document_pipeline.py`）：`documents.processing_status` 狀態機為 `parsing → chunking → embedding → completed/failed`，供前端 Polling 與 `lifespan` zombie task cleanup 判斷用。PDF 走 `pdf_parser.py`（pdfplumber）、XLSX 走 `xlsx_parser.py`（pandas），任一解析失敗都會 fallback 到 `LlamaParseAdapter`。兩條 pipeline chunking 完成後都收斂到共用尾段 `_embed_and_store_chunks`：先呼叫 `services/embeddings.py`（OpenAI native SDK，`text-embedding-3-small`）取得向量，成功才透過 `ChunksRepository.bulk_insert` 把 chunk（含 embedding）寫入 `document_chunks`；embedding API 失敗會直接標記文件 `failed`，不留下沒有向量、DenseRetriever 永遠檢索不到的殘影 chunk。

**Zombie task cleanup**（`services/zombie_cleanup.py`）：只在 FastAPI `lifespan` 啟動時跑一次（見 `main.py`），不是常駐排程；把卡在 `parsing`/`chunking`/`embedding` 且 `updated_at` 超過 timeout 的文件標記 `failed`，防止 `BackgroundTasks` 容器崩潰造成前端無限 Polling。

**檢索**（`adapters/retrievers.py`）：`DenseRetriever` 是 `BaseRetriever` 唯一實作，把「產生 query embedding」與 `ChunksRepository.match()` 串起來。`match()` 呼叫 Postgres RPC `match_document_chunks`（見 `supabase/migrations/20260903120000_match_document_chunks_function.sql`），Metadata Filter（`tenant_id` 必要、`departments`/`confidentiality` 可選）在 SQL function 內部套用、跟 pgvector cosine 排序一起執行——不可在 Python 端用 `.eq()` 事後過濾，否則 planner 無法把 filter 跟向量排序一起最佳化，selective filter 還可能讓 top-k 少於預期筆數。`RRFFusionRetriever` 依 Guardrail #2 只以註解形式存在。

**雙層權限隔離**：`tenant_id` 是硬邊界，交給 Supabase RLS（`documents_rls_policies.sql`），用 pgTAP（`supabase/tests/*.test.sql`）驗證；role-based/confidentiality 過濾是業務規則，留在 FastAPI Query 層（`dependencies/auth.py` 的 `get_current_user`/`require_role` 依賴、`DenseRetriever.retrieve()` 的 `role` 參數），一律用 Pytest + mock repo 驗證（見 Guardrail #6：禁止 Python 直連 DB 測試）。`tenant_id`/`role` 來源是 Supabase Auth JWT 的 `app_metadata`（`get_current_user` 用 `SUPABASE_JWT_SECRET` 驗證簽章後解出），不是使用者可自行宣稱的 header（見 roadmap Day 7.5，取代原本的 dev-identity header 信任機制）。`public.profiles` table（見 `20260904090000_create_profiles_table.sql`）由 `handle_new_user` trigger 從 `auth.users` 同步，是正規化的使用者資料（給 pgTAP 測試與未來管理介面用），不是 RLS 或後端授權判斷的來源。

**雙軌分類鎖**（`documents.classification_status`）：`pending_auto → auto_labeled → manually_verified`。`DocumentsRepository.reorganize()` 升級為 `manually_verified`，`unlock_bulk()`（限 Admin）降級回 `auto_labeled`；`services/classification.py` 的 `on_file_reupload()` 處理「內容變更但已鎖定」的情況——雜湊不符且原狀態為 `manually_verified` 時觸發 `flag_for_review`（目前為 log 佔位，待 Day 9-10 接 Gmail 通知），刻意不自動解鎖。

**前端串接**（`frontend/lib/api.ts` + `app/documents/`）：`request()` 是唯一的 fetch 包裝層，帶 `AuthProvider`（`lib/auth-context.tsx`）目前 session 的 `access_token` 當 `Authorization: Bearer` header 打後端；`app/documents/page.tsx` 用 TanStack Query 讀 `listDocuments()`，`reorganize`/`unlock` 走 mutation 後 `invalidateQueries(["documents"])` 觸發重新抓取——沒有獨立的 polling 元件，狀態更新一律靠 Query 重新 fetch，符合 Guardrail #3（非 Chat 端點禁止 SSE）。角色能不能整理/解鎖是前端（`EDITOR_ROLES`/`role === "admin"`，`role` 從 `useAuth()` 的 JWT `app_metadata` 解出）與後端各自判斷一次，前端這層純粹是 UX 遮罩，真正的授權邊界仍在後端（見上方雙層權限隔離）。
