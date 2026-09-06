# Enterprise AI Knowledge & Report Assistant

企業級 RAG（Retrieval-Augmented Generation）知識問答助手：多租戶文件上傳解析、pgvector 向量檢索、雙模式問答（Chat / Report），搭配角色權限與分類鎖機制。

完整規格請見：
- [`docs/spec_v3.1.md`](docs/spec_v3.1.md) — 完整設計理由與規格
- [`CLAUDE.md`](CLAUDE.md) — 每次開發都必須遵守的 Guardrail 與開發指令速查
- [`docs/adr/`](docs/adr/) — 架構決策紀錄（ADR）

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
supabase/
  migrations/      Schema 與 RLS policy
  tests/           pgTAP（RLS/RBAC 驗證）
docs/
  spec_v3.1.md
  adr/
```

## 快速開始

三個子系統（Supabase 本地環境／後端／前端）各自的啟動指令、環境變數位置、測試指令，統一列在 `CLAUDE.md` §8「開發指令」，這裡不重複——避免兩處文件內容漂移。

## API 文件

後端啟動後（預設 `http://localhost:8000`），FastAPI 自動產生的互動式文件在：

- Swagger UI：`http://localhost:8000/docs`
- ReDoc：`http://localhost:8000/redoc`

目前已實作的端點（`app/main.py` 掛載）：

| 方法 | 路徑 | 說明 |
| :---- | :---- | :---- |
| POST | `/api/documents/upload` | 上傳 PDF/XLSX，觸發解析/切分/向量化 pipeline |
| GET | `/api/documents` | 列出當前租戶文件（含處理狀態、分類狀態） |
| GET | `/api/documents/{id}/status` | 查詢單一文件處理狀態（前端 Polling 用） |
| GET | `/api/documents/{id}/chunks` | 查詢文件的 chunk 列表 |
| GET | `/api/documents/{id}/citation` | 查詢 Citation 詳情 |
| POST | `/api/documents/reorganize` | 手動整理分類（Editor/Admin） |
| POST | `/api/documents/unlock` | 解鎖分類鎖（Admin only） |
| POST | `/api/query` | 知識問答，SSE 串流回應 |
| GET | `/health` | 健康檢查 |

所有端點皆需 `Authorization: Bearer <Supabase JWT>`；`tenant_id`/`role` 從 JWT `app_metadata` 解出，詳見 `CLAUDE.md`「雙層權限隔離」章節。
