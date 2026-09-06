# 前端頁面優化與整合計畫書 — 對照 login_page_sample.png / homepage_sample.png

> 狀態：**Step 0～Step 4 全部已實作並手動驗證通過**，本計畫全部完成。目前 roadmap 進度為 **Day 7.5 已完成**（Supabase Auth JWT 遷移），Day 8（Report Mode）尚未開始。本計畫定位為 Day 7.5 → Day 8 之間的「視覺打磨」任務，不新增後端功能、不影響任何 Day 的 DoD。
>
> 已與使用者確認：首頁「最近更新文件」小清單（原 §3.2 可選項）**納入本次範圍**，非日後才做。
>
> **Step 0/1 實作紀錄**：
> - `globals.css` 主色改為靛藍（3.0），`--radius` 微調為 `0.75rem`。
> - 新增 `app/(dashboard)/layout.tsx` 側邊導覽（3.1），`page.tsx`／`documents/`／`chat/` 已搬入 `(dashboard)` route group（URL 路徑不變）；首頁同步簡化，移除與側邊導覽重複的連結與登出按鈕。
> - 登入頁（3.3）已加上 Logo 區塊、輸入框圖示、密碼顯示/隱藏切換、滿版主色按鈕、淡靛藍背景。
> - **額外修正一個既有 bug**：`components/ui/card.tsx` 原本用 Tailwind v4 專屬語法（`gap-(--card-spacing)`、`*:[img]:...`、`has-data-[slot=x]:...`），但專案裝的是 Tailwind v3.4.1，導致 `Card`/`CardHeader`/`CardContent` 之間完全沒有間距（此問題在登入頁重製時才顯現，原本的極簡版面剛好沒露餡）。已改寫成 v3 相容語法，視覺效果不變，`documents/upload` 頁的 Card 也一併受益。
> - 已用本地 Supabase 建立一個臨時測試帳號登入驗證側邊導覽/active 樣式/既有頁面皆正常，驗證後已刪除該帳號，不留殘餘資料。
>
> **Step 2 實作紀錄**：首頁改為「工作區總覽」（`app/(dashboard)/page.tsx`），統計卡片（總文件數/已完成/處理中/失敗）與「最近更新文件」清單皆從既有 `listDocuments()` 在前端 derive，未新增任何後端端點；狀態色採 emerald/amber/red 對應完成/處理中/失敗。已用一筆真實測試文件（`test_document.pdf`, completed）驗證卡片數字與清單渲染正確。
>
> **環境發現（與本次改版無關，僅供留意）**：驗證時發現本機 `localhost:8000` 被一個**找不到對應 Windows PID 的舊後端進程**佔用（`netstat` 看得到 LISTENING，但 `Get-Process`/`taskkill` 都找不到該 PID，研判與 WSL2 mirrored networking 有關），且該進程回應 `422 X-Tenant-Id header required`——代表它是 **Day 7.5 JWT 遷移前**的舊版後端，並非本次前端改版造成。目前已改用 8010 埠驗證並在驗證後關閉；`localhost:8000` 上的舊進程仍在（無法從 Windows 端終止），之後要用預設 8000 埠跑後端前，建議重開機或請使用者自行從有權限的環境（例如直接關閉 Docker Desktop 或重啟 WSL）清掉它。
>
> **Step 3 實作紀錄**：抽出共用模組 `lib/document-status.ts`（`PROCESSING_STATUS_LABEL`／`STATUS_BADGE_CLASS`／`deriveDocumentStats`）與 `components/stat-card.tsx`，首頁與 `documents/page.tsx` 共用同一份定義，避免重複程式碼；`documents/page.tsx` 頂部加上與首頁一致的 4 張統計卡片（複用同一個 `["documents", session?.user.id]` queryKey，不額外發請求）、依副檔名（.pdf/.xlsx）加上色彩區分的圖示、處理狀態 Badge 改用 `STATUS_BADGE_CLASS` 的 emerald/amber/red 慣例（取代原本的 `secondary`/`destructive` variant），並新增「全部/已完成/處理中/失敗」client-side 篩選按鈕群組（沿用現有 `Button`，未新增 `Tabs` 依賴）。
>
> **Step 3 驗證紀錄**：這次是全新 session，發現本機 Docker Desktop 與 Supabase 本地 stack 皆未啟動（研判上次 session 結束後環境曾重置/重開機，連前次記錄的「卡住的舊 8000 進程」這次也已不存在）。重新啟動 Docker Desktop → `supabase start` → 全新 `uvicorn` (8000) → `npm run dev` (3000) 後，用一次性的 4 筆測試文件（涵蓋 completed/embedding/failed 三種狀態、pdf/xlsx 兩種副檔名、一筆 `manually_verified` 鎖定分類）驗證統計卡片、圖示、色彩 Badge、篩選按鈕皆正確運作；驗證後已刪除測試文件與臨時帳號。**過程中額外修正一個環境問題**：`frontend/.env.local` 的 `NEXT_PUBLIC_API_BASE_URL` 在上次 session 被暫時改成 `http://localhost:8010` 做驗證，但收尾時實際上**沒有還原**（先前記錄誤植為「已還原」），導致這次一開始 documents/首頁資料一直卡在載入中；已改回 `http://localhost:8000` 並重啟前端 dev server 確認正常。目前 Supabase 本地 stack、後端（8000）、前端（3000）皆維持啟動狀態，供接續 Step 4 使用。
>
> **Step 4 驗收紀錄**：沿用 Step 3 驗證留下的本地環境（Supabase/後端/前端皆維持啟動），重建一次性測試帳號，走一次 Day 5 DoD 的完整路徑：(1) 在 `/documents/upload` 上傳 `docs/test_document.pdf`，Polling 狀態依序顯示「查詢中 → 產生向量中 → 已完成」（綠色勾勾圖示），符合 §1 Guardrail「進度更新僅用 Polling」；(2) 在文件列表頁對該文件按「整理」填入分類，確認畫面即時從「尚未分類」變成實線框＋鎖頭的「人工鎖定」（`manually_verified`），且出現「解鎖」按鈕；按「解鎖」後正確降級為虛線框的「AI 自動標籤」（`auto_labeled`），分類值保留、全程透過 `invalidateQueries` 更新畫面，沒有拖拽動畫；(3) 回到首頁工作區總覽，統計卡片與「最近更新文件」清單即時反映新上傳的文件與最新分類狀態。三項均正常，**確認 Step 0-3 的視覺重構沒有造成任何功能回歸**。驗證後已刪除測試上傳的文件（`document_chunks` 透過 `on delete cascade` 一併清除）與臨時帳號。

---

## 1. 現況基準

| 頁面 | 檔案 | 現況 |
|---|---|---|
| 登入 | `frontend/app/login/page.tsx` | Shadcn `Card` + `Form`，單純 email/password，功能已符合 Day 7.5 範疇 |
| 首頁 | `frontend/app/page.tsx` | 純文字標題 + 3 條連結，無資訊呈現 |
| 文件列表 | `frontend/app/documents/page.tsx` | 原生 `<table>`，已有處理狀態 Badge、分類鎖 Badge（虛線/實線+鎖頭），Admin 操作欄 |
| Chat | `frontend/app/chat/page.tsx` | SSE 串流 + Citation 可點擊標籤 |

現有 `components/ui/`：`badge` `button` `card` `form` `input` `label` `select`。尚未安裝 `table` `tabs` `avatar` `dropdown-menu` `separator`。

`lib/api.ts` 目前**沒有**聚合統計端點；`listDocuments()` 回傳完整清單，任何「總數/完成數/失敗數」卡片都必須從既有清單在前端 derive，不能假設有新的後端 API。

---

## 2. 兩張參考圖分析：可採用 vs 不可採用

兩張圖是典型的「企業級 SaaS」視覺基準，但內容本身描繪的是一個**遠超本專案範疇**的產品（多雲端向量庫、多資料連接器、SSO）。逐條對照 `CLAUDE.md`：

### 2.1 login_page_sample.png

| 圖中元素 | 判定 | 理由 |
|---|---|---|
| 卡片置中版型、Logo+標語、輸入框圖示、主色按鈕 | ✅ 可採用 | 純視覺樣式，不涉及功能範疇 |
| Okta SSO / Google Workspace / Microsoft Entra ID 登入 | ❌ 不採用 | §1 技術棧僅列 Supabase Auth；roadmap Day 7.5「明確不做：OAuth/SSO」 |
| FIDO2 YubiKey 硬體金鑰 | ❌ 不採用 | 同上，超出 Day 7.5 範疇，且無對應後端支援 |
| 「忘記密碼？請洽 IT Helpdesk」 | ❌ 不採用 | Day 7.5「明確不做：忘記密碼流程」；放一個點了沒反應的連結對使用者是誤導 |
| 「記住此受信任設備 14 天」 | ❌ 不採用 | 無對應 session 延長機制，Supabase Auth 預設 session 行為之外的宣稱會失真 |
| SOC2 Type II / ISO 27001 稽核聲明 | ❌ 不採用 | 這是**未持有的合規認證**，即使是 Demo/作品集也不應顯示虛假合規聲明，與功能範疇無關，是誠信問題 |

**結論**：只保留版型與元件風格（卡片、圖示輸入框、主色 CTA 按鈕），登入邏輯維持現有 email/password 單一路徑。

### 2.2 homepage_sample.png

| 圖中元素 | 判定 | 理由 |
|---|---|---|
| 頂部統計卡片（總數/健康度/待處理）+ 圖示 | ✅ 可採用（改用真實資料） | 版型可用，但「142,850 篇 / 3.8M Vectors / 99.4%」是虛構數字；本專案要改成從 `listDocuments()` 實際 derive 的總數/完成數/處理中/失敗數 |
| 已連線資料來源卡片（Notion/Confluence/GitHub/Data Warehouse） | ❌ 不採用 | §1 文件解析僅 PDF/XLSX 手動上傳，無任何第三方連接器規劃；roadmap 完全沒有這類 Day |
| Pinecone + Milvus / 1536 dim | ❌ 不採用 | §1 檢索一律 pgvector（`DenseRetriever`），禁止引入額外向量資料庫 |
| 「Claude 3.5 Sonnet / Cohere Rerank v3」模型路由列 | ❌ 不採用 | §1 AI 一律 OpenAI GPT-4o + `text-embedding-3-small`；Guardrail 禁止獨立部署的 reranker 服務、禁止暗示存在 RRF/rerank 邏輯（`RRFFusionRetriever` 僅能以介面存在） |
| 「全部立即同步 (Sync All)」按鈕 | ❌ 暫不採用 | 對應功能是 roadmap **Day 9-10** 的 `POST /admin/sync-knowledge-base`，且該端點設計是外部 Cron 觸發、非使用者手動按鈕；Day 8 之前放這顆按鈕等於跳做後續 Day 功能 |
| 文件分塊與向量管線進度表格（檔名/來源/分塊策略/狀態/動作圖示） | ✅ 部分採用 | 表格版型、狀態 pill、行內動作圖示可套用到現有「文件列表」頁；但欄位要換成本專案實際擁有的資料（來源固定是「手動上傳」、分塊策略固定是「500 tokens+100 overlap」或「XLSX Schema-First」，不做多來源篩選） |
| 進度條 `68%`／`animate-spin` 圖示 | ✅ 可採用（僅限既有 Polling） | 這是 Tailwind 內建 utility class 動畫，非 Guardrail #8 禁止的「拖拽動畫/複雜 DOM 動態效果」；套在既有 Day 5 的 2 秒 Polling 狀態上即可，不新增互動邏輯 |
| 側邊欄多模組導覽（知識庫/檢索分析/權限與合規/模型路由） | ❌ 不採用 | 對應功能（檢索可觀測性儀表板、模型路由設定）都不在 14 天 roadmap 內；只留現有三個真實頁面（上傳/列表/Chat） |

**結論**：首頁改造成「工作區總覽」，用真實文件清單 derive 出的統計卡片 + 既有三個功能入口，不做假資料看板、不做多連接器管理介面。

---

## 3. 視覺風格總則（貼合參考圖 + SaaS 慣例）

使用者要求整體風格盡量貼合兩張參考圖並符合一般 SaaS 產品觀感。以下訂出具體、可落地的 Design Tokens 與版型規則（仍全部用現有依賴實作，不新增套件）：

### 3.0 色彩 Token（`app/globals.css`）

目前是 shadcn 預設的黑白灰主題（`--primary: oklch(0.205 0 0)`，接近純黑），與參考圖的靛藍/紫色主色差距很大。改成貼近圖片的靛藍色系：

| Token | 現況 | 改為（貼近參考圖） |
|---|---|---|
| `--primary` | 近黑 `oklch(0.205 0 0)` | 靛藍 `oklch(0.51 0.23 264)`（約 `#4f46e5` 附近） |
| `--primary-foreground` | 近白 | 純白，不變 |
| `--ring` / focus 邊框 | 灰 | 同 `--primary` 色相，淺一階 |
| `--background`（僅登入頁背景） | 純白 | 極淺薰衣草灰 `oklch(0.98 0.01 264)`，對應圖中登入頁的淡紫背景；其餘頁面維持白底卡片、灰底頁面背景 |
| `--sidebar` / `--sidebar-primary` | 灰階 | 同步套用靛藍主色，供 3.1 導覽列使用 |
| 狀態色（新增，非 shadcn 內建 token，直接用 Tailwind 既有色階） | 無統一規則 | 完成=`emerald`、處理中=`amber`、失敗=`red`（既有 `destructive`）、未分類/待處理=`muted` |

`--radius` 維持現有 `0.625rem` 或可微調到 `0.75rem`，貼近圖片卡片的圓角幅度；不需要額外調整。

### 3.1 全域導覽（新增，跨頁共用）

現況三個功能頁（首頁/文件列表/Chat）彼此沒有共用導覽，只有首頁有連結、登出按鈕也只在首頁——這與參考圖「側邊欄常駐導覽 + 右上角使用者資訊」的 SaaS 慣例不符，也是實際的可用性缺口。新增一個**只含真實功能項目**的共用導覽外殼：

- 型式：仿圖片的左側窄側邊欄（Logo/系統名稱 + 3 個導覽項目：知識問答／文件列表／上傳文件 + 底部使用者資訊與登出），套用在 `(app)` 這類已登入頁面群組的 layout，登入頁不套用。
- 導覽項目**僅止於本專案實際存在的 3 個功能**，不比照圖片放「檢索可觀測性與分析」「權限安全與合規」「模型路由與設定」——這些對應功能都不存在，放上去會變成假導覽。
- 當前頁面用主色高亮（背景淺靛藍 + 左側色條），呼應圖片的 active 樣式。
- 右上角/側邊欄底部顯示登入者 email 與角色（`useAuth()` 已有 `role`），取代現在只在首頁出現的 `SignOutButton`。
- 技術上是新增一個 `app/(dashboard)/layout.tsx`（Next.js Route Group）包住 `page.tsx`／`documents/`／`chat/`，不影響 `login/` 的路由與 `middleware.ts` 既有保護邏輯。

### 3.2 卡片與統計元件樣式

- 統計卡片：仿圖片「圖示置於淺色圓底、右上角」+「大數字＋小標籤」版型，用現有 `Card` 元件排版即可，不需新元件。
- 表格列狀態：用色彩對應（3.0 狀態色）+ 現有 `Badge`，不新增 icon 套件外的依賴。
- 陰影/邊框：卡片統一用 Tailwind `shadow-sm border` 的柔和陰影，避免無邊框的純平面感，貼近圖片卡片的立體感。

以上風格規則會套用到下列 3.3–3.6 各頁面。

### 3.3 登入頁（`app/login/page.tsx`）
- 維持 `supabase.auth.signInWithPassword` 單一登入路徑，不新增任何按鈕分支。
- 視覺調整：置中卡片加上 Logo 區塊（純圖片/CSS，不需新元件）、輸入框加前綴圖示（`lucide-react` 已是專案依賴）、主色 CTA 按鈕滿版。
- 移除／不新增：多 IdP 按鈕、忘記密碼連結、合規聲明區塊。
- 工作量：小（純樣式調整，沿用現有 `Form`/`Card`/`Input`/`Button`）。

### 3.4 首頁（`app/page.tsx` → 「工作區總覽」）
- 沿用 `documents` 頁已在用的 `listDocuments()`（TanStack Query `useQuery`），在首頁**重新取一次同一支 API**（不新增後端端點），前端用 `reduce` 算出：
  - 總文件數 / `completed` 數 / 處理中（`parsing`+`chunking`+`embedding`）數 / `failed` 數
- 用 4 張 `Card` 呈現上述統計（版面仿圖中卡片，但數字全部真實）。
- 下方保留現有三個入口（上傳/列表/Chat），改成可點擊卡片而非純文字連結。
- 列出「最近更新的 5 筆文件」小清單（依 `updated_at` 排序取前 5 筆），複用同一份 `listDocuments()` 資料，不額外打 API。
- 不做：連接器卡片、向量庫統計、模型路由列、Sync 按鈕。

### 3.5 文件列表頁（`app/documents/page.tsx`）
- 頂部加统计卡片（同 3.2 邏輯，複用同一份 query 結果，避免重複發請求可考慮把 `listDocuments` query 提到共用 hook）。
- 表格視覺升級：依副檔名加圖示（PDF/XLSX 兩種，對應 §1 僅支援的格式）、狀態欄用色彩區分的 `Badge`（沿用現有 `PROCESSING_STATUS_LABEL`）、既有分類鎖 Badge 維持不動（已符合規格 §4.2）。
- 可選：簡單的狀態篩選（全部/已完成/處理中/失敗）用按鈕群組做 client-side filter，不必新增 `Tabs` 依賴、不做伺服器端分頁（目前資料量小，分頁是過度設計）。
- 不做：多來源篩選、加密保護欄位、Ingestion Throughput 等虛構指標。

### 3.6 元件依賴與互動規則
- 圖示：全部用專案已依賴的 `lucide-react`，不新增圖示套件。
- 新增元件評估：
  - 值得裝：無（`table` 可用現有 `<table>`+Tailwind 達成，不必為了美觀新增依賴）
  - 不建議裝：`tabs`（client filter 用按鈕群組即可）、`dropdown-menu`（3.1 導覽列的登出目前只有單一動作，用單顆按鈕即可，不必做選單）
- 互動規則：一律「按鈕/篩選 + `router.refresh()` 或 `invalidateQueries`」，不用 `framer-motion`、不做拖拽排序，符合 Guardrail #8。

---

## 4. 明確不在本次範圍（留給對應 roadmap Day 或直接否決）

| 項目 | 原因 |
|---|---|
| SSO / OAuth / FIDO2 登入 | Day 7.5 明確排除 |
| 忘記密碼／Email 驗證信 | Day 7.5 明確排除 |
| 多資料來源連接器（Notion/Confluence/GitHub/Data Warehouse） | 不在 14 天 roadmap 任何 Day，等同新產品範疇 |
| 向量庫統計看板（Pinecone/Milvus/多維度） | §1 僅 pgvector，禁止暗示其他向量庫 |
| Rerank/模型路由 UI | Guardrail #2 禁止獨立 reranker；LLM 固定 GPT-4o，不做路由選擇 UI |
| 「立即同步」手動按鈕 | 對應後端是 Day 9-10 的外部 Cron 端點，現階段（Day 8 之前）加這顆按鈕算跳做後續 Day |
| SOC2/ISO27001 等合規標章 | 未持有的認證，不應顯示，與 Guardrail 無關但屬誠信問題 |

---

## 5. 執行分期建議

| 階段 | 內容 | 狀態 |
|---|---|---|
| Step 0 | 色彩 Token 調整（`globals.css`）+ 新增 `(dashboard)` 導覽 layout | ✅ 已完成 |
| Step 1 | 登入頁視覺重製 | ✅ 已完成 |
| Step 2 | 首頁改造為工作區總覽（含統計卡片＋最近更新清單邏輯） | ✅ 已完成 |
| Step 3 | 文件列表頁視覺升級（圖示、Badge 色彩、可選篩選） | ✅ 已完成 |
| Step 4 | 手動走一次 Day 5 DoD 既有驗收（上傳→Polling→標籤樣式）確認沒有回歸 | ✅ 已完成 |

全部可在**一天內**完成，建議排入 roadmap 文件中原本就規劃的「Day 5 後 buffer」或直接視為 Day 7.5 收尾項目，**不建議**另開新的 roadmap Day（範疇太小，且不涉及任何後端變動）。

---

## 6. Guardrail 自我檢查清單（動工後逐項核對）

- [ ] 沒有新增 SSO/OAuth 按鈕或忘記密碼流程
- [ ] 沒有新增假資料統計（所有數字都來自 `listDocuments()` 實際回傳）
- [ ] 沒有出現 Pinecone/Milvus/Cohere Rerank/模型路由等字樣
- [ ] 沒有新增「立即同步」等提前呼叫 Day 9-10 端點的按鈕
- [ ] 沒有顯示未持有的合規認證標章
- [ ] 互動全部是按鈕/篩選 + 既有 Query 機制，沒有拖拽動畫或新動畫套件
- [ ] 沒有新增不必要的 shadcn 元件依賴
- [ ] 新導覽列只有 3 個真實功能項目，沒有比照圖片放「檢索分析／權限合規／模型路由」等不存在的模組

---

## 7. 確認事項（已與使用者核對）

1. 本次先只產出計畫書，**不立即動手實作**；待使用者後續明確指示再開始 Step 1-4。
2. 首頁「最近更新文件」小清單**納入本次範圍**（非可選項）。
