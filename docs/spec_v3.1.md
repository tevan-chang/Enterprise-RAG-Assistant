# Enterprise AI Knowledge & Report Assistant

## 專案規格書 v3.1（最終可行性修訂版 + Delta 整合）

> **修訂記錄**：本版整合原 v3.1 canonical 內容，並疊加一份 Delta Summary（部署架構、Gmail API 通知、Schema-First Token 優化、增量同步端點）。整合原則：架構合理、複雜度可控的項目直接納入正文；有 Scope Creep 風險的項目納入但標註「Day 9-10 Buffer / 非核心展示路徑」，避免排擠 §13 兩分鐘 Demo 劇本的核心三畫面。標註方式見各節內文中的 `⚠️ Scope 提醒`。

> **v3.1 核心降維與精準打擊修訂**（相較 v3）：
>
> 1. **檢索機制**：MVP 收斂為 pgvector Dense Search + Metadata Filter，以 Adapter Pattern 抽象 `BaseRetriever`，預留 `RRFFusionRetriever` 擴充介面
> 2. **文件解析範疇**：收斂為 PDF + XLSX 雙主線，暫停 PPTX/DOCX
> 3. **DB 測試策略**：RLS/RBAC 驗證改為 Supabase CLI + pgTAP
> 4. **E2E 測試分層**：Playwright 收斂為 1 條 Happy Path，其餘改 Pytest API 合約測試
> 5. **前端範疇**：聚焦 2 分鐘 Demo 劇本 3 大核心畫面

---

## 0. 專案定位

**工程深度優先，以有意識的技術取捨能力為核心設計原則。**

- 核心目的：在 2 週內產出工程深度足以支撐技術審查的 MVP，展現「有意識的技術取捨能力」而非功能堆疊
- 商業可行性（多租戶、計費、SaaS 化）作為架構完整性的佐證存在，不是開發優先序的驅動依據
- 角色框架：一人團隊開發，需在有限的開發資源與時程下完成。所有技術選型須說明「為何選擇 / 學習成本 / 開發成本 / 維運成本」；若功能設計超出此框架可負擔範圍，必須主動說明「這超出 MVP 階段」並提出精簡替代方案

**產品定位**：結合智慧 RAG 檢索、PDF/XLSX 文件解析、結構化報告生成（Report Mode，含 bounded tool-calling）、精確 Citation 溯源、雙軌（自動/手動）檔案整理與防覆蓋狀態鎖機制、Gmail API 事件通知、外部 Cron 增量同步，以及 SaaS 多租戶架構的企業級 AI 助理系統。

---

## 1. 技術棧（已鎖定）

| 分類 | 技術 | 選型理由 |
| :---- | :---- | :---- |
| 後端 | Python 3.11+, FastAPI (async/await), Pydantic v2, Uvicorn | 高效非同步 I/O，適合 RAG 與 LLM 串流 |
| 資料庫/CLI | PostgreSQL + pgvector (Supabase Local CLI → **Supabase Cloud** 正式環境) | 本地模擬，極速部署與型別生成 |
| 認證/隔離 | Supabase Auth + JWT + RLS | DB 原生層強制跨租戶隔離硬邊界 |
| 前端 | Next.js 14 (TypeScript, App Router), Tailwind CSS, Shadcn UI | 搭配 CLI 自動生成型別，現成元件快速拼裝核心畫面 |
| **前端部署** | **Vercel** | 原生 Next.js 14 App Router 託管，Edge Network SSR/ISR 加速與 Git PR Preview Deploy |
| **後端部署** | **Render (Docker Web Service)** | 獨立 Python 容器環境，原生支援長連線 SSE 串流與 `pandas`/`pdfplumber` 密集型 CPU 運算，避免 Serverless Timeout |
| AI | OpenAI GPT-4o, text-embedding-3-small | 標準化高表現力 LLM & Embedding；**一律 Native OpenAI SDK，不引入 LangChain/LlamaIndex/Haystack** |
| 文件解析（主線） | pdfplumber（PDF）, pandas（XLSX） | PDF 負責文本與頁碼 Citation，XLSX 負責結構化表格與運算 |
| 文件解析（Fallback） | LlamaParse | 解析異常一律觸發，轉嫁邊界例外處理責任 |
| 檢索 | pgvector (Dense) + Metadata Filter + Adapter Pattern | MVP 做 dense 語意檢索，代碼預留 RRF 擴充介面 |
| **通知 / GCP 整合** | **Google API Client (`google-api-python-client`)** | Gmail API (Service Account / OAuth 2.0) 發送非同步郵件，展現 GCP 憑證管理與事件驅動架構能力 |
| Observability | Sentry | 接住 BackgroundTasks 與 Tool-calling 失敗路徑 |
| 測試框架 | pgTAP（DB/RLS）, Pytest（API 合約）, Playwright（1 條 E2E） | DB 原生測試 + API 合約測試 + 核心流程 E2E |
| 部署 | Docker Compose（本地）+ Vercel/Render（正式） | 本地單一指令啟動，正式環境前後端分離部署 |

### 明確禁止

- Kubernetes / Kafka / Elasticsearch
- 微服務架構 / Event Sourcing / 複雜 DDD
- Celery 或任何獨立 broker + worker 架構（**Zombie Task 由 lifespan health check 處理，見 §2.1**）
- 任何以獨立可部署服務形式存在的 reranker
- 無邊界的 Agent loop（多步規劃、reflection、持續 loop）
- **LangChain / LlamaIndex / Haystack 等高階 RAG 框架**（Prompting、Chunking、Tool-calling 一律手寫 Native SDK）
- 應用層內建 `rank_bm25` 倒排索引
- PPTX/DOCX 解析
- 前端複雜拖拽動畫 / 自訂 DOM 動態效果
- 超出一人開發維運能力的基礎設施
- **常駐 Scheduler / 應用內排程器**（增量同步一律由外部 GitHub Actions Cron 觸發，見 §5）
- **憑證硬編碼**（Gmail API 憑證一律讀環境變數，禁止寫死於 repo）

### 1.1 Claude Code 開發工具鏈規則

- **Context7**：生成涉及 pgvector 語法、Supabase RLS policy、FastAPI BackgroundTasks edge case、Next.js 14 App Router API、Gmail API scopes 前，強制先查 Context7 取得當前版本文件，禁止憑訓練記憶生成版本敏感 API
- **Pydantic v2 語法強制**：一律使用 `@field_validator`、`model_config`；禁止生成 v1 棄用語法（如 `@validator`、`class Config`）

---

## 2. 架構修正決策

### 2.1 背景任務：Celery → FastAPI BackgroundTasks（+ 崩潰防禦 + Gmail 通知）

```python
@router.post("/documents/upload")
async def upload_document(file: UploadFile, background_tasks: BackgroundTasks):
    doc = await save_document(file)
    background_tasks.add_task(auto_classify, doc.id)  # in-process，無需額外服務
    return {"document_id": doc.id, "status": "processing"}
```

- 前端透過 `processing_status` 欄位（`parsing → chunking → embedding → completed/failed`）短間隔 Polling（每 2 秒）取得進度
- Guardrail：僅在實測吞吐量瓶頸出現時才考慮升級 Celery，不可預先實作

**Startup Health Check（Zombie Task Cleanup）**：

於 FastAPI `lifespan` 啟動階段加入檢查。若 DB 中有 `classification_status IN ('parsing', 'chunking')` 且 `updated_at` 超過 10 分鐘，自動更新為 `failed` 並紀錄 Sentry，避免前端無限期 Polling。這是 `BackgroundTasks` 相對 Celery 最大的已知弱點（容器崩潰即 Task Loss），必須有防禦機制才站得住腳。

**Gmail API 非同步通知服務（`GmailAPINotificationAdapter`）**：

- 以 Adapter Pattern 抽象 `BaseNotificationService`，經由 `google.oauth2` 載入 GCP Credentials，將 HTML 內容做 URL-safe Base64 編碼後發送
- 由 FastAPI `BackgroundTasks` 非同步派發，發送失敗交由 Sentry 捕捉，**絕不阻塞 API 主回應**（維持與原 Demo 版「單次 call，失敗直接回傳錯誤」相同的複雜度量級，只是把 webhook 換成 Gmail API，不加 retry queue）
- 發送情境與對象：
  1. `DOCUMENT_PROCESSED`：背景解析完成 → 通知**上傳者本人**
  2. `FLAG_FOR_REVIEW`：已鎖定檔案內容變更 → 警報通知 **Admin**
  3. `RAG_SYNC_COMPLETED`：外部 Cron 增量同步完成 → 發送報告給 **Admin**

> ⚠️ **Scope 提醒**：GCP Service Account / OAuth 2.0 憑證申請與 Scope 設定屬一次性 setup 成本，非程式碼複雜度，但仍建議排在 **Day 9-10 buffer**，不佔用 Day 6-9 核心路徑（Chat/Citation/Report Mode）。若時間吃緊，可先用 `logger.info` stub 替代實際發送，介面（`BaseNotificationService`）不變，Adapter 設計的完整性不受影響。

### 2.2 檢索架構：pgvector Dense + Metadata Filter（路線 B，取代原 Hybrid+RRF 主線）

**問題**：`rank_bm25` 為應用層記憶體內倒排索引，在多 worker / 服務重啟情境下需要額外處理索引同步與持久化，這項成本在 2 週單人時程下不成比例。企業文件多半具備明確部門與命名規範，可用 Metadata Filter 先縮小搜尋池，再做 pgvector 語意計算，精準度與效能足以撐起 Demo。

**設計**：以 Adapter Pattern 抽象 `BaseRetriever`，MVP 僅實作 `DenseRetriever`，`RRFFusionRetriever` 留作未來擴充介面（不實作，只留 interface 位置）：

```python
class BaseRetriever(ABC):
    @abstractmethod
    async def retrieve(self, query: str, tenant_id: str, top_k: int = 5) -> list[dict]:
        pass

class DenseRetriever(BaseRetriever):
    """MVP 階段：Supabase pgvector + Metadata Filter"""
    async def retrieve(self, query: str, tenant_id: str, top_k: int = 5) -> list[dict]:
        # 1. 依 departments / final_categories / tenant_id 做 Metadata Filter 縮小搜尋池
        # 2. 對縮小後的集合做 pgvector 語意相似度排序
        ...

# 未來擴充位（不在 MVP 範疇內實作）：
# class RRFFusionRetriever(BaseRetriever): ...
```

- 架構圖標註「Retrieval Adapter (DenseRetriever, MVP) — 未來可插拔 RRFFusionRetriever」
- 取捨理由另行整理

### 2.3 進度更新機制：Polling，不用 SSE

- SSE 保留給 Chat 查詢（打字機效果）作為核心差異化賣點
- 文件處理進度使用短間隔 Polling（每 2 秒 `GET /documents/{id}/status`）
- 即時性需求高的地方（Chat）才用 SSE，低頻更新場景（進度條）刻意選 Polling，避免過度工程

### 2.4 Report Mode：擴充 Bounded Tool-Calling（+ Schema-First Token 優化）

**問題定位**：XLSX 已解析為結構化 Markdown Table，但 LLM 對表格做加總/比較/跨文件數值運算不可靠，這是真實限制而非為展示編造的情境。

**設計原則**：能用單輪 function calling 解決的問題，不上完整 Agent 框架。

**兩個 tool**：

| Tool | 功能 | 說明 |
| :---- | :---- | :---- |
| `query_documents` | 既有 DenseRetriever 檢索包裝成 explicit function call | 讓 Report Mode 檢索動作變成 LLM 主動決策 |
| `compute_table_metric` | 對已解析 XLSX 結構資料做 pandas 運算 | 複用既有 XLSX 解析管線 |

**XLSX Schema-First Strategy（Token 優化）**：

XLSX 解析**不將全量表格塞入 Context**，僅向 LLM 傳送「Schema 摘要（Sheet 名、欄位名、型態、Top-3 Sample）」。LLM 依此生成計算意圖（column + operation），後端透過 `compute_table_metric`（pandas）執行精確運算，節省 80% 以上 Token，同時避免大表格截斷導致的運算誤差。

**邊界**：

- 最多 1-2 輪 tool call，不做多步規劃、不做 reflection、不做持續 loop
- 取捨理由另行整理

**錯誤處理**：

```python
async def compute_table_metric(doc_id: str, column: str, operation: str) -> dict:
    try:
        result = await run_pandas_operation(doc_id, column, operation)
        return {"status": "success", "result": result}
    except (ColumnNotFoundError, TypeError) as e:
        return {"status": "error", "error_type": type(e).__name__, "message": str(e)}
```

失敗路徑串接 §2.5 Sentry。API 不新增端點，`/api/reports/generate` 內部邏輯擴充處理 tool call 輪次。

### 2.5 Observability：Sentry

- FastAPI exception middleware + BackgroundTasks 失敗捕捉（`on_file_reupload` 的 `flag_for_review` 路徑、embedding API 失敗、§2.4 tool call 失敗路徑、§2.1 Gmail 發送失敗路徑）
- Next.js error boundary
- 用途：接住真實會發生的錯誤路徑，Demo 現場故障可即時定位並附具體 trace

---

## 3. 權限控管與安全機制（RBAC）

### 3.1 混合式分工

| 隔離範疇 | 實作層 | 原因 |
| :---- | :---- | :---- |
| **tenant_id 隔離**（跨租戶硬邊界） | Supabase RLS | 硬邊界交給 DB 層強制執行 |
| **role-based confidentiality filter**（業務規則） | FastAPI Query 層 | 業務邏輯留在 Python 便於快速迭代與測試 |

```python
if current_user.role == "viewer":
    query = query.where(Document.confidentiality != "restricted")
```

### 3.2 三層角色

- **Admin**：全域權限，可上傳/刪除檔案、批次解鎖 AI 分類標籤、檢視全租戶用量、觸發 `/admin/sync-knowledge-base`
- **Editor**：可上傳與編輯授權範圍內知識庫檔案、建立 Report
- **Viewer**：僅限提問與檢索，無權上傳、修改標籤或觸發背景解鎖重整
- `unlock` 動作限 Admin

### 3.3 文件機密等級

- Metadata：`public` / `internal` / `restricted`
- RAG 自動過濾：檢索時後端依發問者 Role 自動附加 Metadata Filter（如 Viewer 檢索時自動排除 `confidentiality = 'restricted'`）

### 3.4 RLS/RBAC 測試：Supabase CLI + pgTAP（取代 Python 直連 DB 測試）

```sql
BEGIN;
SELECT plan(1);
-- 模擬 JWT Context (Tenant A + Viewer)
SET LOCAL request.jwt.claims = '{"sub": "user_1", "app_metadata": {"tenant_id": "tenant_a", "role": "viewer"}}';
SELECT is_empty('SELECT * FROM documents WHERE confidentiality = ''restricted''');
SELECT finish();
ROLLBACK;
```

測試矩陣：role（3）× confidentiality（3）× tenant 交叉（同租戶/跨租戶）× CRUD 四種操作，透過 `supabase test db` 於 CI 執行。

---

## 4. 資料庫結構

### 4.1 Document Metadata Schema

```json
{
  "document_id": "doc_2026_99b",
  "file_name": "2026年第二季財報.xlsx",
  "file_path": "/財務部/2026預算/",
  "auto_categories": ["財務", "報表"],
  "manual_categories": ["2026核心資料"],
  "final_categories": ["2026核心資料"],
  "classification_status": "manually_verified",
  "file_content_hash": "e3b0c44298fc1c149afbf4c8996fb...",
  "tenant_id": "tenant_12345",
  "departments": ["財務部"]
}
```

### 4.2 雙軌分類鎖機制

- 狀態機：`0: pending_auto → 1: auto_labeled → 2: manually_verified 🔒`
- 自動分類（AI 鋪底）：檔案上傳/更新時，背景任務呼叫輕量 LLM 解析並寫入 `auto_categories`
- 手動整理（最高優先權）：前端編輯標籤，寫入 `manual_categories`，同步更新 `final_categories`
- 背景自動分類排程必須加過濾條件 `classification_status != 2`
- 手動變更後自動轉為狀態 2，Admin 可後台發起條件式批次解鎖

### 4.3 file_content_hash 觸發邏輯

```python
async def on_file_reupload(doc_id: str, new_content: bytes):
    new_hash = hashlib.sha256(new_content).hexdigest()
    doc = await get_document(doc_id)
    if doc.file_content_hash != new_hash and doc.classification_status == "manually_verified":
        await flag_for_review(doc_id)  # 不自動解鎖，交由 Admin 判斷，並觸發 Gmail 警報通知
```

---

## 5. API 端點規格

| Method / Path | 說明 |
| :---- | :---- |
| POST /api/documents/upload | PDF/XLSX 上傳與解析（含 fallback 邏輯）；上傳前依 `file_content_hash` 比對同租戶內是否已有相同內容的文件，命中回 409（不比檔名）；內容不同但檔名相同時也回 409（`reason: filename_exists`），可帶 `force=true` 略過 |
| POST /api/documents/{doc_id}/reupload | 使用者選擇「覆蓋既有文件」時呼叫：更新 file_content_hash、清除舊 chunks、重新跑一次解析 pipeline；hash 有變且原本 manually_verified 時觸發 flag_for_review（見 §4.3），不自動解鎖 |
| POST /api/documents/reorganize | 手動改名/編輯標籤，狀態鎖升級為 2 |
| POST /api/documents/unlock | 批次解鎖，狀態鎖降級為 1 |
| DELETE /api/documents/{doc_id} | 刪除檔案並觸發向量 Cascade 清理 |
| GET /api/documents/{doc_id}/status | 處理進度 Polling |
| POST /api/query | Chat 模式，SSE 串流回應 |
| POST /api/reports/generate | Report 模式，DenseRetriever 檢索 + bounded tool-calling |
| **POST /api/v1/admin/sync-knowledge-base** | 供外部 Cron（GitHub Actions）帶 API Key 觸發的自動化 RAG 增量更新，完成後經 Gmail API 發送報告給 Admin |
| **POST /api/v1/admin/test-notification** | *(Dev/Admin 健檢)* 測試 Gmail API 憑證連線與 MIME 郵件發送狀態 |
| GET /health | Render 防休眠 Ping 端點（見 §16.3） |

> ⚠️ **Scope 提醒**：`sync-knowledge-base` 與外部 GitHub Actions Cron 屬於「架構能力展示」而非 §13 兩分鐘 Demo 劇本的必要畫面 —— 建議實作但**不排入現場演示**，視需要另行展示/口述，避免壓縮 Chat/Citation/Report Mode 的打磨時間。觸發頻率定為**每日 1 次**（見 `docs/adr/0008-external-cron-over-in-app-scheduler.md`）；`.github/workflows/sync-knowledge-base.yml` 已建立，尚待設定 `SYNC_API_KEY` GitHub Secret 才會真正觸發成功，見 `docs/dev_roadmap_v3.1.md` Day 9-10「待實現清單」。

---

## 6. 前端標籤視覺規則

| 標籤類型 | 邊框樣式 | 圖示 (lucide-react) | 語意 |
| :---- | :---- | :---- | :---- |
| AI 自動標籤 (auto_labeled) | 虛線 dashed | Wand2 | AI 鋪底結果，可被覆蓋 |
| 手動標籤 (manually_verified) | 實線 solid | Lock 🔒 | 人工鎖定，AI 排程略過 |

---

## 7. Citation Tracing（範疇對齊 PDF/XLSX 雙主線）

| 文件類型 | Citation 粒度 |
| :---- | :---- |
| PDF | 頁碼（Page） |
| XLSX | 工作表名稱 + 儲存格/欄位範圍（Sheet + Cell Range） |

點擊 Citation 標籤 → 開啟對應文件跳轉至該頁碼/工作表位置。**不做**精確段落文字反白高亮（投資報酬率低，見風險管理）。

```json
{
  "source_doc": "2026年第二季財報.xlsx",
  "sheet": "營收明細",
  "cell_range": "B2:D15",
  "chunk_text_preview": "..."
}
```

---

## 8. 前端開發原則（劇本導向）

- 利用 `supabase gen types typescript --local` 自動生成 DB 型別，前後端型別一致
- 使用 Shadcn UI 快速拼裝，不投入客製化視覺系統
- **不做**複雜 DOM 拖拽動畫；分類/歸檔操作以下拉選單或按鈕觸發，狀態更新透過 `router.refresh()` 或重新讀取 Table 呈現
- 100% 聚焦 2 分鐘 Demo 劇本 3 大核心畫面：
  1. 上傳與標籤狀態顯示（Auto 虛線+Wand2 vs Manual 實線+Lock🔒）
  2. Chat SSE 串流 + Citation 跳轉 Modal/Drawer
  3. Report Mode 報告生成面板（含 tool-calling 過程可視化）

---

## 9. Observability & 測試策略

### 9.1 Sentry（見 §2.5）

生產真實依賴，接住 BackgroundTasks 與 tool-calling 已知錯誤路徑，供現場即時拉取真實 trace 排查。

### 9.2 pgTAP（見 §3.4）

RLS/RBAC 矩陣驗證的主要防線，DB 原生層執行，CI 中先於其他測試跑。

### 9.3 Playwright E2E（收斂為 1 條 Happy Path）

**範疇**：使用者上傳 PDF → 前端 Polling 狀態轉為 Completed → 頁面出現 Auto 標籤（虛線）。

理由：驗證上傳解析 Pipeline（跨越 BackgroundTasks、Polling、前端渲染三層），是全案最基礎、最該有信心的一條路徑；LLM 串流/tool-calling 涉及非確定性輸出，不適合作為 E2E 斷言對象。

### 9.4 Pytest API 合約測試（覆蓋原本規劃的其餘 3 條流程）

以 `httpx.AsyncClient` 直打 API，斷言 response schema 與關鍵欄位，覆蓋：

- Chat SSE 串流（斷言事件流格式與最終訊息完整性）
- Citation 文件層級跳轉（斷言回傳的 `source_doc`/`page`/`sheet` 欄位正確）
- Report Mode tool-calling（斷言 tool call 觸發與錯誤路徑的結構化回應）
- Gmail 通知發送（mock Gmail API client，斷言 payload 結構與失敗路徑 Sentry 捕捉）

---

## 10. Demo 版 vs 完整版功能複雜度對照表

| 功能 | ❌ 不做（完整版） | ✅ 做（Demo 版） |
| :---- | :---- | :---- |
| 檢索架構 | Hybrid Search（Dense+BM25+RRF） | pgvector Dense + Metadata Filter，Adapter 預留 RRF 介面 |
| 文件格式覆蓋 | PDF/DOCX/PPTX/XLSX 全支援 | PDF + XLSX 雙主線，其餘走 LlamaParse fallback 或延後 |
| Token 計費 | 真實計費結算邏輯 + 月結週期 | 每次 API call 累加 token 數寫入 DB，前端即時算 cost |
| **Email / Gmail 通知** | 完整通知系統 + retry queue + template 管理 | **單次 Gmail API 非同步 call，失敗直接回傳 Sentry（無 retry）** |
| **知識庫增量同步** | 應用內常駐 Scheduler + 版本管理 UI | 單一 API Key 端點，外部 GitHub Actions Cron 觸發 |
| RLS/RBAC 驗證 | 全量整合測試 | pgTAP DB 原生矩陣測試 |
| E2E Testing | 全流程 Playwright 覆蓋 | 1 條 Happy Path + Pytest API 合約測試補其餘 |
| 前端互動 | 拖拽動畫、複雜 DOM 效果 | 下拉選單/按鈕觸發 + router.refresh() |
| 背景分類任務 | Celery + 獨立 worker | FastAPI BackgroundTasks + lifespan zombie cleanup |
| Report Mode Tool-Calling | 多步規劃 Agent / LangGraph | Bounded 1-2 輪 function calling，Schema-First Token 優化 |
| 部署架構 | K8s / 自建 CI-CD Pipeline | Vercel（前端）+ Render（後端）+ 外部 Ping 防休眠 |

---

## 11. 風險管理與應對方案

| 風險項目 | 潛在影響 | 緩解與應對方案 |
| :---- | :---- | :---- |
| AI 背景分類覆蓋人工整理結果 | 分類與目錄結構被破壞 | `classification_status` 狀態鎖，自動排程嚴格過濾 |
| PDF/XLSX 解析格式錯位 | Chunk 品質差，檢索準確度下降 | 主線僅設計目標為格式規整文件，任何解析異常一律觸發 LlamaParse Fallback |
| RLS Policy 正確性錯誤 | 資安漏洞，跨租戶/跨角色資料外洩 | pgTAP DB 原生矩陣測試，Week 1 Day 1-2 優先處理 |
| Citation 精確高亮投資報酬率低 | 排擠高風險項時間 | 明確不做段落高亮，只做頁碼/Sheet 跳轉 |
| 應用層 BM25 索引同步/持久化複雜度 | 多 worker 環境索引不一致，重啟遺失狀態 | 移除應用層 BM25，改用 DB 原生 pgvector + Metadata Filter |
| 多格式解析範疇過大排擠核心時程 | PPTX/DOCX edge case 侵蝕核心打磨時間 | 收斂為 PDF+XLSX 雙主線 |
| E2E 測試因 LLM 非確定性導致 CI 不穩定 | Demo 前夕 CI 紅燈難排查 | E2E 僅留 1 條無 LLM 涉入的 Happy Path |
| Multi-Query 檢索 Token 爆炸 | LLM API 成本過高或請求超時 | 單次報告最多 3-5 個子查詢，Top-K (K=3) 截斷；XLSX 走 Schema-First |
| RAG 產生幻覺 | 回答不準確 | Prompt 強制約束「未檢索到內容須回答不知道」 |
| file_content_hash 誤解鎖 | 人工分類成果被覆蓋 | 改為 `flag_for_review`，不自動解鎖 |
| Tool-calling 範疇蔓延 | 演變成需維護的完整 Agent 框架 | 嚴格限制 1-2 輪 |
| Demo 現場故障難以即時定位 | 現場無法即時解釋 bug 成因 | Sentry 即時捕捉 |
| **BackgroundTasks 容器崩潰導致 Task Loss** | 前端無限期 Polling，狀態卡死 | `lifespan` Startup Health Check 掃描殭屍任務，10 分鐘逾時自動標記 `failed` |
| **Gmail OAuth/GCP 憑證設定耗時排擠核心開發** | 佔用 Day 6-9 核心路徑 | 排入 Day 9-10 buffer，時間吃緊可先用 log stub 替代，Adapter 介面不變 |
| **Render 免費層冷啟動延遲** | Demo 現場首次請求延遲，觀感差 | 外部排程（Cron-job.org/UptimeRobot）每 10 分鐘 ping `/health` 維持 Hot State |

---

## 12. 功能優先順序與時程（2 週，Day-by-Day）

### 第 1 週：Supabase CLI、解析管道、pgvector 檢索與雙軌 API

- **Day 1-2**：Supabase CLI 環境搭建 + RLS Policy + pgTAP 測試腳本（風險項優先，其餘子系統建立在正確隔離之上）
- **Day 2-3**：PDF（pdfplumber）與 XLSX（pandas）主線解析管線 + LlamaParse Fallback + `lifespan` Zombie Task Health Check
- **Day 3-5**：pgvector 表結構與 Chunking（500 tokens+100 overlap）；DenseRetriever + Metadata Filter API；雙軌整理 API（reorganize/unlock）與 Shadcn UI 基礎畫面

### 第 2 週：雙模式問答、Report Mode（Tool-calling）、Citation、部署與 Sentry

- **Day 6-7**：`/api/query`（SSE 串流 Chat）+ Citation 文件層級跳轉 API
- **Day 8-9**：`/api/reports/generate`（Bounded tool-calling + Schema-First pandas 運算）；Sentry 接入
- **Day 9-10（Buffer）**：Gmail API 通知 Adapter（或 log stub）；`sync-knowledge-base` 端點；Vercel/Render 部署 + CORS/環境變數設定 + `/health` 防休眠
- **Day 10**：1 條 Playwright Happy Path E2E；Pytest API 合約測試補齊；Docker Compose 本地打包；2 分鐘 Demo 劇本演練

---

## 13. 商業價值與展示效益

### 13.1 商業價值評估

- 檔案維運自動化：AI 自動分類打底節省人工整理時間，管理者保有 100% 最終修改與鎖定權利
- 財務/營運場景：上傳部門預算表（XLSX）與制度文件（PDF），進行跨文檔數值比對與合規診斷
- 事件通知：關鍵狀態變更（處理完成、需複審、同步完成）主動觸達，降低人工巡檢成本
- SaaS 商業落地：多租戶資料隔離 + 使用量計費模擬

### 13.2 2 分鐘黃金展示劇本

- **[0:00-0:30]** 上傳 PDF/XLSX，展示自動分類（虛線+Wand2）；手動改標籤，展示鎖頭（實線+🔒）
- **[0:30-1:15]** Chat 問答：SSE 串流回答，點擊 Citation 標籤跳轉至對應 PDF 頁碼或 XLSX 工作表位置
- **[1:15-1:45]** Report Mode：輸入跨文檔問題，展示 LLM 呼叫 `compute_table_metric` 進行 XLSX 數值比較（tool-calling 實例），產出結構化報告
- **[1:45-2:00]** SaaS 多租戶與計費展示：租戶剩餘 Quota 扣抵動態

> Gmail 通知與增量同步為架構加分項，不佔用現場 2 分鐘劇本時間，留待後續 Q&A 展示。

---

## 14. 回答模式（Claude 在此 Project 中的行為準則）

當被問及功能實作時，依序：

1. 評估對「系統完整性與工程展示效果」的貢獻
2. 分析實作難度（相對於初階自學背景可負擔的合理複雜度）
3. 提供 Demo 版本方案（對照 §10 表格）
4. 直接生成可運行代碼（無偽代碼）
5. 若功能有完整版/簡化版落差，明確標註採用哪個版本及原因
6. 若出現過度設計傾向，主動否決並替代

**明確 Guardrail 清單**：

- 背景任務一律用 BackgroundTasks，並在 `lifespan` 加入殭屍任務清理
- 檢索一律用 DenseRetriever（pgvector+Metadata Filter），不生成應用層 BM25 索引邏輯，RRF 相關程式碼僅能出現在 `RRFFusionRetriever` 介面註解，不實作內容
- 進度更新一律用 Polling，SSE 僅限 Chat 查詢
- 文件解析僅處理 PDF/XLSX，其餘格式一律走 LlamaParse fallback 或標記為未來擴充，不生成 PPTX/DOCX 解析代碼
- 涉及 pgvector/RLS/BackgroundTasks/Next.js App Router/Gmail API 的程式碼，生成前先查 Context7
- Tool-calling 一律 bounded（1-2 輪），出現多步規劃需求視為超出 MVP 範疇並提出替代方案
- RLS 驗證一律用 pgTAP，不生成 Python 直連 DB 測試檔
- E2E 測試僅涵蓋上傳解析 Happy Path，其餘流程一律用 Pytest API 合約測試，不擴充 Playwright 涵蓋範圍
- 前端不生成拖拽動畫或複雜 DOM 動態效果的程式碼
- **嚴禁引入 LangChain、LlamaIndex、Haystack 等高階 RAG 框架**，所有 Prompting、Chunking 與 Tool-calling 一律手寫 OpenAI Native SDK
- **強制使用 Pydantic v2 語法**（如 `@field_validator`），禁止生成 v1 棄用代碼
- **Gmail API 發送郵件須使用 `google-api-python-client`**，憑證讀取自環境變數，嚴禁將憑證 JSON 硬編碼或寫死在 repo 內
- **不生成應用內常駐 Scheduler**，增量同步邏輯一律走外部 Cron 觸發的 API 端點

---

## 15. 未來架構可擴充性（非本階段開發依據）

- **Hybrid Search**：`RRFFusionRetriever` 實作 `BaseRetriever` 介面即可插入，呼叫端無需改動
- **PPTX/DOCX 解析**：透過 Parser Adapter 擴充，不影響現有 PDF/XLSX pipeline
- **前端拖拽動畫與進階互動**：待核心功能驗證後再投入視覺打磨
- **動態部門組織樹**：MVP 預留 `departments: []` 欄位，未來可串接企業 HR/LDAP 系統，實現多層級跨部門遞迴權限繼承
- **A/B 測試差異比對面板**：模型/Prompt 升級後比較新舊分類結果，儲存版本快照並提供比對 UI，非 2 週 MVP 範疇
- **通知系統升級**：Gmail API 單次 call → 完整 retry queue + template 管理系統
- **增量同步升級**：外部 Cron 觸發 → 應用內排程 + 版本快照管理 UI
- 若專案轉向真實商業驗證，可重新引入數據驅動決策機制；Agent/n8n 完整整合維持 P2/P3

---

## 16. 部署與 DevOps 架構（Vercel + Render）

### 16.1 前後端分離部署架構

- **前端（Vercel）**：託管 Next.js 14 App Router，享有 Edge Network 靜態快取與 Git Pull Request Preview Deploy。**已部署**：`https://frontend-ten-virid-56.vercel.app`
- **後端（Render）**：FastAPI Docker Web Service，獨立處理 Python 數據分析（pandas）、PDF 解析與 OpenAI API 長連線 SSE 串流。**已部署**：`https://enterprise-rag-backend-43lh.onrender.com`（`/health` 已驗證回應 200）
- **資料庫（Supabase Cloud）**：PostgreSQL + pgvector + Supabase Auth

### 16.2 CORS 與環境變數規範

- **FastAPI（Render）白名單**：`allow_origins=["https://frontend-ten-virid-56.vercel.app"]`
- **Vercel 環境變數**：`NEXT_PUBLIC_API_BASE_URL=https://enterprise-rag-backend-43lh.onrender.com`

### 16.3 Render 免費版防休眠機制（Ping Mechanism）

外部排程服務（Cron-job.org / UptimeRobot）每 10 分鐘自動發送 HTTP GET 至 API `/health` 端點，維持後端容器處於 Hot State，避免 Demo 時遭遇冷啟動延遲。

> ⚠️ **Scope 提醒**：此為維運層面的補丁，不涉及應用內程式邏輯，實作成本極低（一個 `/health` 端點 + 外部服務設定），可直接納入 Day 10 打包流程，不佔用核心開發時間。
>
> **現況**：已在 Cron-job.org 設定排程任務（「RAG Assistant Backend Health Ping」），每 10 分鐘 GET `https://enterprise-rag-backend-43lh.onrender.com/health`，已驗證執行成功（985 ms），防休眠 ping **已實際運作**。

---

## 附錄：v3 → v3.1 → v3.1+Delta 修訂總表

| 項目 | v3 | v3.1 | v3.1 + Delta |
| :---- | :---- | :---- | :---- |
| 檢索架構 | Hybrid（Dense+BM25+RRF），RRF 演算法直接實作 | pgvector Dense + Metadata Filter，Adapter Pattern 預留 RRF 介面（不實作） | 不變 |
| 文件格式 | PDF/DOCX/PPTX/XLSX 全支援 | 收斂為 PDF + XLSX 雙主線 | 不變 |
| RLS 測試 | Python 直連 DB test suite | Supabase CLI + pgTAP，SQL 原生層 | 不變 |
| E2E 範疇 | 4 條核心流程 | 1 條 Happy Path，其餘改 Pytest API 合約測試 | 不變 |
| 前端範疇 | 含拖拽資料夾 UI | 3 大核心畫面，不做複雜拖拽動畫 | 不變 |
| Citation 粒度 | 頁碼/Slide | 頁碼（PDF）/ Sheet+Cell Range（XLSX） | 不變 |
| 背景任務韌性 | 未定義 | FastAPI BackgroundTasks | + `lifespan` Zombie Task Health Check |
| 通知機制 | 未定義 | 未定義 | + Gmail API Adapter（單次非同步 call，無 retry） |
| 增量同步 | 未定義 | 未定義 | + 外部 Cron 觸發的 `/admin/sync-knowledge-base` |
| Report Mode Token 優化 | 未定義 | 未定義 | + XLSX Schema-First Strategy |
| 部署架構 | 未定義 | Docker Compose（本地） | + Vercel（前端）/ Render（後端）正式部署 |
| RAG 框架邊界 | 未定義 | 未定義 | + 明確禁止 LangChain/LlamaIndex/Haystack |
| 取捨論述整理 | 分散於各章節 | 獨立成 §14 Interview Playbook，四則 QA（此節於後續版本移出公開文件） | 擴充為八則 QA |
