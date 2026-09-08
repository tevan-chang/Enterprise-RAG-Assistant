---
description: 將 frontend/ 的 Next.js 專案部署到 Vercel，並回傳正式網址
---

將本地 `frontend/` 目錄的 Next.js 14 專案部署到 Vercel（正式環境）。

## 步驟

1. 切換到 `frontend/` 目錄，確認 `package.json` 內有 `next` 依賴。
2. 確認 Vercel CLI 登入狀態：執行 `npx vercel whoami`。
   - 若未登入，提示使用者自行執行 `npx vercel login` 完成瀏覽器/Email 授權（這是需要人工互動的步驟，不要代為猜測或跳過），完成後再繼續。
3. 若 `frontend/.vercel/project.json` 不存在，執行 `npx vercel link --yes` 建立/連結 Vercel 專案。
4. 對照 `frontend/.env.local.example` 確認 Vercel 專案的 Production 環境變數已設定：
   - `NEXT_PUBLIC_API_BASE_URL`
   - `NEXT_PUBLIC_SUPABASE_URL`
   - `NEXT_PUBLIC_SUPABASE_ANON_KEY`
   - `NEXT_PUBLIC_SENTRY_DSN`
   可用 `npx vercel env ls production` 檢查，缺少的用 `npx vercel env add <NAME> production` 逐一從本機 `frontend/.env.local` 對應值匯入（一次一個，不要把整份 `.env.local` 印到終端機或貼進對話）。
5. 執行正式部署：`npx vercel --prod --yes`。
6. 從指令輸出擷取正式網址（`https://*.vercel.app` 或自訂網域），回報給使用者。
7. 若部署失敗，依序檢查：環境變數是否缺漏、本地 `npm run build` 是否能過、Vercel 專案框架偵測是否為 Next.js。

## 注意事項

- 部署是會影響外部可見狀態的動作，執行前先確認要部署的分支/commit 是否正確（預設用當前工作目錄的內容）。
- 環境變數一律用 `vercel env add` 逐一匯入，不要整份貼出 `.env.local` 內容。
- 完成後只回報最終網址與部署狀態，不必贅述中間步驟的完整 log。
