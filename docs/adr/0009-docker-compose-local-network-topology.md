# 0009. Docker Compose 本地網路拓撲：不吃案 Supabase 的 compose、固定 Auth Cookie 名稱

## Context

Day 10 要求 `docker compose up` 一鍵啟動本地全棧（見 `dev_roadmap_v3.1.md` Day 10）。本機 Supabase 已經是 Supabase CLI 另外管理的一套獨立 docker-compose 專案（`supabase start`），這裡浮現兩個設計問題：

1. `docker-compose.yml` 要不要把 Supabase 的 service 也吃案進來一起定義？
2. backend/frontend container 內部要怎麼連到 host 上跑的本機 Supabase？

實作過程中，(2) 又牽出一個沒預料到的第三個問題：`frontend/middleware.ts` 在 container 內部驗證 session 時，若跟瀏覽器端用不同的 Supabase URL（見下方 Decision），會導致登入後被導回登入頁——用 Playwright E2E（見 `e2e/tests/upload-happy-path.spec.ts`）跑起來直接重現，不是靠 code review 看出來的。

## Decision

**(1) 不把 Supabase 折進這份 docker-compose.yml**，只定義 `backend`/`frontend` 兩個 service。Supabase 本身是 CLI 另外管理的完整 compose 專案（postgres/auth/kong/storage/realtime 等十幾個 service），兩份 compose 檔案疊在一起管理只會增加複雜度，且不是 spec §16 的設計意圖——前提是使用者要先手動 `supabase start`。

**(2)** backend/frontend container 內部一律用 Docker Desktop 內建的 `host.docker.internal`（搭配 `extra_hosts: ["host.docker.internal:host-gateway"]` 確保 Linux Docker 也適用）連回 host 上的本機 Supabase（`http://host.docker.internal:54321`），瀏覽器端則直接用 `http://localhost:54321`（Supabase CLI 發佈在 host 的埠）。

**(3)** `middleware.ts` 因此多讀一個非 `NEXT_PUBLIC_` 前綴的 `SUPABASE_URL_INTERNAL` 環境變數，只給 container 內的 server 端驗證 session 用（`NEXT_PUBLIC_*` 會在 build time 被 inline 成字面值，無法在 runtime 依環境切換；非 public 變數則會在 middleware 執行當下才讀 `process.env`，天生就適合這種「同一份程式碼、依部署環境切換網路路徑」的需求）。非 Docker 環境（`npm run dev`）不設定這個變數，直接 fallback 回 `NEXT_PUBLIC_SUPABASE_URL`。

**(4) 固定 auth cookie 名稱**：`@supabase/ssr` 預設用傳入的 Supabase URL 的 host 推導 auth cookie 名稱（例如 `http://localhost:54321` → `sb-localhost-auth-token`）。瀏覽器端與 middleware 用不同 host（`localhost` vs `host.docker.internal`）會算出兩個不同的 cookie 名稱，導致 middleware 永遠讀不到瀏覽器寫入的 session cookie、一律判定未登入。解法是雙邊都顯式帶 `cookieOptions: { name: "sb-auth-token" }`（見 `frontend/lib/supabase/client.ts` 匯出的 `SUPABASE_AUTH_COOKIE_NAME` 常數，`middleware.ts` 引用同一個常數），繞開 host 推導邏輯，這是 `@supabase/ssr` 官方文件記載的標準用法（`cookieOptions.name`），不是繞過安全機制的 hack。

## Consequences

**取得的好處**：
- Docker Compose 的職責邊界清楚：只管應用程式自己的兩個服務，Supabase 的生命週期完全交給 Supabase CLI，符合單一職責、也符合這個專案一路以來「不重造官方工具已經做好的事」的取捨傾向。
- `SUPABASE_URL_INTERNAL` 的 fallback 設計讓同一份 `middleware.ts` 程式碼不需要為了 Docker 環境另外分支或重寫，本機裸跑（多數開發時間用的模式）完全不受影響。

**付出的代價**：
- 多一個環境變數（`SUPABASE_URL_INTERNAL`），是 Docker Compose 本地開發這個場景特有的複雜度，正式部署（Vercel + Render 各自直連同一個 Supabase Cloud URL，沒有 container 對外/對內視角不一致的問題）不會遇到。
- `cookieOptions.name` 固定寫死這件事本身**不是** Docker-only 的改動——`frontend/lib/supabase/client.ts` 是所有環境共用的同一份瀏覽器 client 工廠，固定 cookie 名稱後，任何環境（含正式 Vercel/Render 部署）裡帶著舊格式 cookie（`sb-<project-ref>-auth-token`）的既有 session，下次請求會被 middleware 判定找不到對應 cookie 而強制登出一次。這個專案目前還沒有正式使用者流量，這個一次性的代價可以忽略，但如果之後有真實使用者在線上環境登入過，部署這個改動當下要有心理準備會清空既有 session。

## 常見問題與回答依據

- 「為什麼不把 Supabase 也塞進 docker-compose.yml？」→ 見上方 Decision (1)：Supabase CLI 自己就是一整套 compose 專案，重複定義只會增加要顧的 moving part，跟 0002/0008 的「不自找額外維運成本」是同一套判斷邏輯。
- 「這個 cookie 名稱不一致的 bug 是怎麼抓到的？」→ 不是 code review 看出來的，是 Day 10 補的 Playwright E2E（`e2e/tests/upload-happy-path.spec.ts`）在本地 docker compose 環境下跑，登入後直接被導回登入頁，才動手用 `console.log` 逐層排查到 middleware 的 `getUser()` 回傳「Auth session missing」——這也是為什麼 Guardrail #7 要求至少留一條真正端到端的 Playwright 測試，不是所有東西都能靠單元測試 mock 掉發現的。
- 「這個修法是不是繞過了 Supabase 的安全機制？」→ 不是，`cookieOptions.name` 是 `@supabase/ssr` 官方文件記載的公開設定項（見官方 `_autodocs/configuration.md`），本來就是設計給「需要自訂 cookie 名稱」的情境用，這裡只是用官方支援的方式讓兩邊算出同一個名稱。
- 屬於 roadmap Day 10 任務，2026-09-10 完成並用 Playwright E2E 實測驗證通過。
