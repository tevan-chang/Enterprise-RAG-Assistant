# Enterprise AI Knowledge & Report Assistant

[![CI](https://github.com/tevan-chang/Enterprise-RAG-Assistant/actions/workflows/ci.yml/badge.svg)](https://github.com/tevan-chang/Enterprise-RAG-Assistant/actions/workflows/ci.yml)

企業級 RAG（Retrieval-Augmented Generation）知識問答助手：多租戶文件上傳解析、pgvector 向量檢索、雙模式問答（Chat / Report），搭配角色權限與分類鎖機制。

完整規格請見：
- [`docs/spec_v3.1.md`](docs/spec_v3.1.md) — 完整設計理由與規格
- [`CLAUDE.md`](CLAUDE.md) — 每次開發都必須遵守的 Guardrail 與開發指令速查
- [`docs/adr/`](docs/adr/) — 架構決策紀錄（ADR）

## 功能特色

- **多租戶隔離**：`tenant_id` 由 Supabase RLS 在 DB 層強制隔離，role-based／confidentiality 過濾則在 FastAPI 層做第二層檢查（雙層權限隔離）
- **文件解析管線**：PDF（pdfplumber）／XLSX（pandas）自動解析、切分、向量化，解析異常自動 fallback 到 LlamaParse
- **雙模式問答**：
  - **Chat**：SSE 串流回應，附來源標註（citation）可點擊查看原文位置
  - **Report Mode**：bounded tool-calling（固定 1-2 輪），支援語意檢索與 XLSX 精確數值運算（sum/average/min/max/count），並可在單次呼叫內完成「篩選 + 分組統計 + Top-N」
- **AI 自動分類 + 雙軌分類鎖**：上傳後自動打分類標籤，人工複核後鎖定（`pending_auto → auto_labeled → manually_verified`），內容變更但已鎖定時觸發 Gmail 通知
- **Token 用量追蹤**：即時累計 chat/report/embedding/classification 四類呼叫的 token 用量與估算成本
- **外部 Cron 驅動同步**：不用應用內常駐 Scheduler，改由 GitHub Actions 定時觸發增量同步與孤兒任務清理
- **分層測試策略**：pgTAP（RLS/RBAC）＋ Pytest（API 合約）＋ Playwright（1 條上傳 Happy Path E2E）

## 技術棧

| 分類 | 技術 |
| :---- | :---- |
| 後端 | Python 3.11+, FastAPI (async), Pydantic v2 |
| 資料庫 | PostgreSQL + pgvector（Supabase） |
| 認證/隔離 | Supabase Auth + JWT + RLS |
| 前端 | Next.js 14（App Router, TypeScript）, Tailwind CSS, Shadcn UI |
| AI | OpenAI GPT-4o, text-embedding-3-small（Native SDK） |
| 文件解析 | pdfplumber（PDF）, pandas（XLSX），異常 fallback 到 LlamaParse |

完整技術棧、禁用架構與強制規則見 `CLAUDE.md` §1-§2。

## 目錄結構

```
backend/app/
  routers/        FastAPI 端點（含 RBAC/驗證）
  services/       業務邏輯與 pipeline
  repositories/    Supabase table 存取
  adapters/        外部服務或可替換策略（LlamaParseAdapter、DenseRetriever）
  schemas/         Pydantic request/response
  dependencies/    跨 router 共用依賴（auth.py）
frontend/          Next.js 14 App Router
e2e/               Playwright E2E（獨立專案，橫跨 backend+frontend+Supabase）
supabase/
  migrations/      Schema 與 RLS policy
  tests/           pgTAP（RLS/RBAC 驗證）
docs/
  spec_v3.1.md
  adr/
```

## 快速開始

三個子系統（Supabase 本地環境／後端／前端）各自的啟動指令、環境變數位置、測試指令，統一列在 `CLAUDE.md` §8「開發指令」，這裡不重複——避免兩處文件內容漂移。也可以用 `docker compose --env-file frontend/.env.local up --build` 一鍵啟動 backend + frontend（前置仍是先 `supabase start`），細節同樣在 `CLAUDE.md` §8。

## 部署狀態

- **後端（Render）**：已部署，`https://enterprise-rag-backend-43lh.onrender.com`
- **前端（Vercel）**：已部署，`https://frontend-ten-virid-56.vercel.app`

外部排程現況（見 `docs/dev_roadmap_v3.1.md` Day 9-10「待實現清單」與 `docs/adr/0008-external-cron-over-in-app-scheduler.md`）：
- `/health` 防休眠 Ping：已在 Cron-job.org 設定，每 10 分鐘觸發一次，已驗證正常運作。
- `sync-knowledge-base` 每日 Cron：`.github/workflows/sync-knowledge-base.yml` 已建立並 merge，`SYNC_API_KEY` GitHub Secret 已設定，已用 `gh workflow run` 手動觸發驗證成功。

**Gmail 通知收件人**：`DOCUMENT_PROCESSED`（文件處理完成）動態查上傳者 email 的邏輯已實作（`backend/app/config.py` 的 `use_dynamic_notification_recipient`），但**預設關閉**——個人專案沒有多組測試信箱可以驗證這條路徑，三種通知情境（`DOCUMENT_PROCESSED`／`FLAG_FOR_REVIEW`／`RAG_SYNC_COMPLETED`）目前都固定寄到 `admin_notification_email`（預設值是專案作者本人信箱）。要切換成動態查詢，把 `use_dynamic_notification_recipient` 設 `True`（或設環境變數 `USE_DYNAMIC_NOTIFICATION_RECIPIENT=true`）即可，不需要改程式碼。

## API 文件

本地開發（後端啟動後，預設 `http://localhost:8000`）或正式環境（`https://enterprise-rag-backend-43lh.onrender.com`），FastAPI 自動產生的互動式文件都在對應網址的：

- Swagger UI：`/docs`
- ReDoc：`/redoc`

目前已實作的端點（`app/main.py` 掛載）：

| 方法 | 路徑 | 說明 |
| :---- | :---- | :---- |
| POST | `/api/documents/upload` | 上傳 PDF/XLSX，觸發解析/切分/向量化 pipeline（Editor/Admin） |
| POST | `/api/documents/{id}/reupload` | 覆蓋既有文件內容，重跑 pipeline（Editor/Admin） |
| GET | `/api/documents` | 列出當前租戶文件（含處理狀態、分類狀態） |
| GET | `/api/documents/{id}/status` | 查詢單一文件處理狀態（前端 Polling 用） |
| GET | `/api/documents/{id}/chunks` | 查詢文件的 chunk 列表 |
| GET | `/api/documents/{id}/citation` | 查詢 Citation 詳情 |
| DELETE | `/api/documents/{id}` | 刪除文件（Editor/Admin） |
| POST | `/api/documents/reorganize` | 手動整理分類（Editor/Admin） |
| POST | `/api/documents/unlock` | 解鎖分類鎖（Admin only） |
| POST | `/api/query` | 知識問答，SSE 串流回應 |
| POST | `/api/reports/generate` | Report Mode，bounded tool-calling 產出報告 |
| GET | `/api/usage` | 查詢當前租戶累計 token 用量與估算 cost |
| POST | `/api/v1/admin/sync-knowledge-base` | 外部 Cron 觸發增量同步（`X-API-Key` 驗證，非 JWT） |
| POST | `/api/v1/admin/test-notification` | Gmail 通知健檢（Admin only） |
| GET | `/health` | 健康檢查 |

除 `/health` 與 `/api/v1/admin/sync-knowledge-base`（改用 `X-API-Key` header，供外部 GitHub Actions Cron 呼叫）外，所有端點皆需 `Authorization: Bearer <Supabase JWT>`；`tenant_id`/`role` 從 JWT `app_metadata` 解出，詳見 `CLAUDE.md`「雙層權限隔離」章節。
