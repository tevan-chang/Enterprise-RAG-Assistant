# Enterprise AI Knowledge & Report Assistant — 開發日程
### Canonical: v3.1 + Delta（pgvector Dense-only / PDF+XLSX / pgTAP / Gmail 通知 / Vercel+Render 部署）

> 使用方式：每天結束前對照「DoD」勾選，「Guardrail 檢查」是在 review Claude Code 產出時要特別盯的越界風險。全部來自規格書 §1、§15、§附錄。

---

## 📝 本次修訂異動（相較上一版 roadmap）

依據最新 spec_v3.1.md（整合 Delta Summary：部署架構、Gmail API 通知、Schema-First Token 優化、增量同步端點）調整：

| 異動位置 | 內容 |
|---|---|
| Day 2-3 | 新增 `lifespan` Zombie Task Health Check 任務（§2.1，防 BackgroundTasks 容器崩潰 Task Loss） |
| Day 8 | 明確標註 XLSX Schema-First Strategy（Schema 摘要取代全量表格塞入 Context，節省 80%+ Token） |
| Day 9-10（Buffer）| 大幅擴充：Gmail API 通知 Adapter（或 log stub）、`sync-knowledge-base` / `test-notification` 端點、Vercel+Render 部署、CORS/環境變數、`/health` 防冷啟動 |
| Guardrail 清單 | 新增：Gmail 憑證禁止硬編碼、禁止應用內常駐 Scheduler、pgvector/RLS/BackgroundTasks/Next.js/Gmail API 語法生成前強制查 Context7、Pydantic v2 語法強制 |
| Phase 0 | 新增 `.env.example` 骨架（Gmail credentials、Render/Vercel 環境變數占位） |
| ADR | 建議視時間評估是否加開 `0004-deployment-vercel-render.md`（非必須，取捨論述已於 docs/spec_v3.1.local.md 涵蓋，寫不寫不影響背景說明） |

---

## Phase 0：`/init` 後、Day 1 前置作業（不計入 14 天）

- [ ] 比對生成的 `CLAUDE.md` 與規格書 §1「明確禁止」＋ §15「Guardrail 清單」，補上遺漏的否定式約束
- [ ] `.claude/settings.json` Bash allowlist：`supabase`, `pytest`, `playwright`, `docker compose`（不含 `alembic`，v3.1 用 Supabase CLI 管 migration）
- [ ] Repo skeleton：`backend/`、`frontend/`、`docs/adr/`
- [ ] `supabase init` + `supabase start`，確認 `pgvector` extension 可用
- [ ] Docker Compose skeleton（空殼，Day 10 填實際 service）
- [ ] `.env.example` 骨架：`OPENAI_API_KEY`、`SUPABASE_URL`、`SUPABASE_ANON_KEY`、`GMAIL_SERVICE_ACCOUNT_JSON`（或 OAuth client id/secret）、`SYNC_API_KEY`（供外部 Cron 打 `sync-knowledge-base` 用）、`ALLOWED_ORIGINS`（Render CORS 白名單）— 只放 key 名稱，不放真實值，真實值走 local `.env` 與 Render/Vercel 後台環境變數
- [ ] 開 3 個 ADR stub：`0001-retrieval-dense-only.md`、`0002-backgroundtasks-over-celery.md`、`0003-parsing-scope-pdf-xlsx.md`
- [ ] `git init` + 第一個 commit（skeleton only）

---

## Week 1：Supabase CLI、解析管道、pgvector 檢索、雙軌 API

### Day 1：RLS Policy 設計 + pgTAP 環境
**任務**
- Schema 設計：`documents` table（含 `tenant_id`, `departments`, `classification_status`, `confidentiality`, `file_content_hash`）
- 撰寫 RLS policy：`tenant_id = auth.jwt() ->> 'tenant_id'`
- `supabase test db` 環境跑通，寫第一支 pgTAP 測試（單一 tenant 隔離驗證）

**DoD**：`supabase test db` 綠燈通過至少 1 條跨租戶隔離測試

**Guardrail 檢查**：不要讓 Claude Code 生成 Python 直連 DB 的測試檔案（舊習慣容易復發）

---

### Day 2：RLS Policy 矩陣完成 + pgTAP 覆蓋
**任務**
- 完成 role（Admin/Editor/Viewer）× confidentiality（public/internal/restricted）× tenant（同租戶/跨租戶）矩陣測試
- CI 接入：pgTAP 排在 CI 第一階段（先於其他測試）

**DoD**：矩陣測試全數通過，CI pipeline 骨架建立（即使只有這一個 stage）

---

### Day 3：PDF 解析管線（pdfplumber）+ Zombie Task Health Check
**任務**
- `pdfplumber` 抽取文本 + 頁碼 metadata
- Chunking：500 tokens + 100 overlap
- 解析失敗 → LlamaParse fallback 觸發邏輯
- **新增**：FastAPI `lifespan` 啟動階段掃描 `classification_status IN ('parsing','chunking')` 且 `updated_at` 超過 10 分鐘的紀錄，自動標記 `failed` 並寫 log（之後 Day 9 接上 Sentry）— 這是 BackgroundTasks 相對 Celery 最大弱點的防禦機制，越早補上越好，避免 Day 5 之後 upload pipeline 越長，補測試越麻煩

**DoD**：上傳測試 PDF，能產出帶頁碼的 chunk list；手動塞一筆 `updated_at` 超過 10 分鐘的 `parsing` 假資料，重啟服務後能看到自動轉 `failed`

**Guardrail 檢查**：不要讓 Claude Code 順手把 DOCX/PPTX 解析也生出來（很容易「順便」多做）；不要把 zombie task cleanup 寫成常駐 scheduler（一律 `lifespan` 啟動時跑一次即可，不是背景輪詢）

---

### Day 4：XLSX 解析管線（pandas）
**任務**
- `pandas` 讀取 XLSX，轉結構化 Markdown Table（供之後 Day 8 Schema 摘要用）
- Citation metadata：sheet name + cell range
- 同樣接 LlamaParse fallback

**DoD**：上傳測試 XLSX，能產出帶 sheet+cell range 的結構化 chunk

---

### Day 5：DenseRetriever + Metadata Filter + 雙軌整理 API
**任務**
- `BaseRetriever` ABC + `DenseRetriever` 實作（Metadata Filter 縮小池 → pgvector 語意排序）
- `RRFFusionRetriever` 僅留 class 簽名 + interface 註解，不寫邏輯
- `POST /api/documents/reorganize`、`POST /api/documents/unlock`（Admin only）
- 分類鎖狀態機：`pending_auto → auto_labeled → manually_verified`
- `on_file_reupload`：hash 變更且原狀態為 `manually_verified` → 觸發 `flag_for_review`（不自動解鎖）

**DoD**：DenseRetriever 能對測試租戶回傳 top-k 結果；unlock 端點對非 Admin 回傳 403；reupload 觸發 flag_for_review 而非自動解鎖

**Guardrail 檢查**：確認沒有出現任何 `rank_bm25` import 或倒排索引邏輯

---

## Week 2：雙模式問答、Report Mode、通知/部署、Citation、Sentry

### Day 6：Chat SSE 串流
**任務**
- `POST /api/query`：SSE 串流回應
- Prompt 約束：「未檢索到內容須回答不知道」

**DoD**：前端能收到逐字串流的 chat 回應

---

### Day 7：Citation 跳轉 API
**任務**
- Citation 結構：PDF → page；XLSX → sheet + cell range
- 前端 Modal/Drawer 顯示對應原文片段

**DoD**：點擊 citation 標籤能跳轉到正確頁碼/工作表位置（不做段落高亮，規格書已明確排除）

---

### Day 8：Report Mode Tool-Calling（part 1）+ Schema-First Token 優化
**任務**
- `query_documents` tool：包裝現有 DenseRetriever
- `compute_table_metric` tool：pandas 運算 + try/except 結構化錯誤回應
- **明確落實 Schema-First Strategy**：XLSX 解析結果**不將全量表格塞入 Context**，只送「Sheet 名 + 欄位名 + 型態 + Top-3 Sample」的 Schema 摘要給 LLM；LLM 依此生成計算意圖（column + operation），再由後端 `compute_table_metric` 執行精確運算

**DoD**：LLM 能觸發至少一次 `compute_table_metric` 並拿到正確運算結果；用一份 50+ 列的測試 XLSX 驗證傳給 LLM 的 payload 只有 schema 摘要而非全表（可直接印 token 數對比）

**Guardrail 檢查**：tool call 輪次上限 1-2 輪，不要讓 Claude Code 加入 reflection/多步規劃邏輯；不要為了「方便」把全表格塞進 prompt

---

### Day 9：Report Mode（part 2）+ Sentry 接入
**任務**
- `/api/reports/generate` 整合兩個 tool，串成完整報告輸出
- Sentry：exception middleware + BackgroundTasks 失敗捕捉（含 `flag_for_review`、embedding API 失敗、tool call 失敗路徑、Day 3 zombie task cleanup 路徑）

**DoD**：故意觸發一個 embedding API 失敗，能在 Sentry 看到 trace

---

### Day 9-10（Buffer）：Gmail 通知 + 增量同步端點 + 部署上線
**任務**
- `GmailAPINotificationAdapter`（實作 `BaseNotificationService`）：經 `google.oauth2` 讀環境變數載入憑證，HTML 內容 URL-safe Base64 編碼，掛 `BackgroundTasks` 非同步發送、失敗走 Sentry、不阻塞主回應
  - 若時間吃緊，先用 `logger.info` stub 替代實際發送，介面不變（Adapter 設計的完整性不受影響）
  - 三種發送情境：`DOCUMENT_PROCESSED`（通知上傳者）、`FLAG_FOR_REVIEW`（通知 Admin）、`RAG_SYNC_COMPLETED`（通知 Admin）
- `POST /api/v1/admin/sync-knowledge-base`：帶 API Key 驗證，供外部 GitHub Actions Cron 觸發增量同步，完成後經 Gmail 通知 Admin
- `POST /api/v1/admin/test-notification`：Dev/Admin 健檢端點，測試 Gmail 憑證連線
- `GET /health`：Render 防休眠 Ping 端點
- Vercel 部署前端（Next.js 14）；Render 部署後端（FastAPI Docker Web Service）
- CORS：Render 端 `allow_origins=["https://<app>.vercel.app"]`；Vercel 環境變數 `NEXT_PUBLIC_API_BASE_URL=https://<api>.onrender.com`
- 外部排程（Cron-job.org / UptimeRobot）設定每 10 分鐘 ping `/health`

**DoD**：mock Gmail API 測試三種通知情境的 payload 結構；`sync-knowledge-base` 用假 API Key 打能拿到 401；正式網址能打通前後端（Vercel 呼叫 Render API 成功）；`/health` 能被外部排程 ping 通

**Guardrail 檢查**：Gmail 憑證絕不寫死於 repo（一律環境變數）；不要生成應用內常駐 scheduler 邏輯（增量同步只能是外部 Cron 打 API，不能在 FastAPI 內用 `APScheduler` 之類的東西）；涉及 Gmail API scopes 語法時先查 Context7

---

### Day 10：E2E + Docker Compose + Demo 演練
**任務**
- 1 條 Playwright Happy Path：上傳 PDF → Polling 轉 Completed → 前端出現 Auto 標籤（虛線+Wand2）
- Pytest API 合約測試補齊：Chat SSE 格式、Citation 欄位、Report tool-calling 結構、Gmail 通知 mock payload
- Docker Compose 打包，單一指令跑起全棧（本地開發用；正式環境走 Vercel/Render）
- 2 分鐘 Demo 劇本實際演練 2-3 次，抓 timing（Gmail 通知與增量同步不占用現場 2 分鐘劇本時間，留待 Q&A 展示）

**DoD**：`docker compose up` 一鍵啟動本地環境；Demo 劇本能在 2 分鐘內跑完不出錯；正式部署網址也能完整跑一次 Demo 劇本（確認 Render 冷啟動已被 ping 機制解決）

**Guardrail 檢查**：確認沒有把 Chat/Report/Gmail 通知流程額外寫進 Playwright（規格書明確要求這些走 Pytest 合約測試，避免 LLM 非確定性與外部 API 依賴拖垮 CI）

---

## Buffer（原規格未列，強烈建議留）
2 週單人開發建議在 Day 5 後留半天 buffer，用於：
- PR self-review（尤其 RLS policy，見規格書 §11 高優先風險項）
- 補完 ADR 內容（別留到最後一天生出三篇）
- README + API 文件
- （視時間）評估是否加開 `0004-deployment-vercel-render.md` ADR，對應 §14 新增的部署與通知相關 QA

---

## 每日收尾檢查清單（貼在 CLAUDE.md 或每日對話開頭都可）
- [ ] 今天的 code 有沒有出現規格書 §1/§15 明確禁止的模式（BM25 邏輯、DOCX/PPTX 解析、SSE 用在非 Chat 端點、Playwright 覆蓋到 Chat/Report/Gmail、應用內常駐 Scheduler、Gmail 憑證硬編碼、Pydantic v1 語法）
- [ ] 涉及 pgvector/RLS/BackgroundTasks/Next.js App Router/Gmail API 的程式碼，生成前有沒有先查 Context7
- [ ] 今天的架構決策是否值得寫一篇 ADR
- [ ] 今天寫的 code 能不能用一句話講清楚「為什麼這樣做」（工程取捨的核心精神）
