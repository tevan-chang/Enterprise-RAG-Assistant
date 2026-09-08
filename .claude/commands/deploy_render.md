---
description: 將 backend/ 的 FastAPI 專案部署到 Render（Native Python Web Service），並回傳正式網址
---

將本地 `backend/` 目錄的 FastAPI 專案部署到 Render。目前用 **Native Python runtime**（非 Docker）——backend 還沒有 Dockerfile，Docker 化排在 roadmap Day 10，故此指令先用免 Docker 的方式部署，符合目前進度（見對話紀錄的使用者決定）。

Render 的部署模型是「連結 Git repo」，不像 Vercel 能直接把本機檔案上傳部署，所以第一次部署一定有一段**需要瀏覽器操作的手動步驟**（連結 GitHub），不要試圖用指令繞過或猜測跳過。

## 前置檔案

- 根目錄 `render.yaml`（Blueprint，已建立）：定義 `enterprise-rag-backend` 這個 Web Service，`rootDir: backend`、`buildCommand: pip install -r requirements.txt`、`startCommand: uvicorn app.main:app --host 0.0.0.0 --port $PORT`、`healthCheckPath: /health`，並列出 7 個需要在 Render Dashboard 手動填值的環境變數（`sync: false`）。

## 步驟

1. 確認 `render.yaml` 已 commit 且已 push 到 GitHub（`git push` 到 `origin/master`）——Render 是從 repo 內容讀取 Blueprint，本機沒 push 的話 Render 看不到。
2. 檢查是否已有 `RENDER_API_KEY` 環境變數或 Render CLI（`render --version`）：
   - 若都沒有，代表這是**第一次部署**，需要使用者到 Render Dashboard（https://dashboard.render.com）手動完成一次性設定：
     a. 「New +」→「Blueprint」
     b. 連結 GitHub 帳號/repo `tevan-chang/Enterprise-RAG-Assistant`（第一次會跳 GitHub OAuth 授權，這是人工步驟，不要代為猜測或跳過）
     c. Render 會偵測到根目錄的 `render.yaml`，列出 `enterprise-rag-backend` 服務
     d. 依提示填入 7 個標記 `sync: false` 的環境變數實際值（對照本機 `backend/.env`，一次一個從 Dashboard UI 貼上，不要把整份 `.env` 內容印到終端機或貼進對話）
     e. 額外注意 `ALLOWED_ORIGINS`：要填正式前端網域（例如目前的 Vercel production URL），不是 `http://localhost:3000`，否則部署後前端會被 CORS 擋掉
     f. 按下 Apply，Render 會依 Blueprint 建立服務並開始 build+deploy
   - 若已有 `RENDER_API_KEY`（使用者已在 Render Dashboard → Account Settings → API Keys 產生過，並設成環境變數）且已透過上述方式完成過一次 Blueprint 連結，之後可用 CLI 觸發重新部署：`render deploys create enterprise-rag-backend --wait`（服務名稱以 Render Dashboard 顯示的為準）。
3. 部署完成後，用 `render services` 列出服務或直接到 Dashboard 該服務頁面複製 URL；Render 預設網址格式為 `https://<service-name>.onrender.com`。
4. 用 `curl https://<service-name>.onrender.com/health` 驗證服務有正常回應，再回報網址給使用者。
5. 若 build 失敗，優先檢查：`backend/requirements.txt` 是否能在乾淨環境安裝成功、`rootDir`/`startCommand` 路徑是否正確、7 個環境變數是否都已在 Dashboard 填值（缺任何一個 FastAPI 啟動都可能出錯，因為 `Settings()` 會讀不到必要值）。

## 之後的部署（非第一次）

Blueprint 連結完成後，`autoDeployTrigger: commit` 代表**之後每次 `git push` 到 master，Render 會自動重新部署**，不需要每次都重新執行這支指令或手動觸發。這支指令主要用在：第一次建立服務、或需要手動立即重新部署（不想等下次 push）時。

## 注意事項

- 部署是會影響外部可見狀態的動作，且第一次會建立新的 Render 服務（會產生費用視方案而定），執行前跟使用者確認要部署的 repo/分支是否正確。
- 環境變數的實際值一律透過 Render Dashboard UI 或 `render env` 系列指令逐一設定，不要把 `backend/.env` 整份印出。
- 這是 Native Python 部署（非 Docker）。若之後 roadmap Day 10 做完 Docker 化，要改用 Dockerfile 部署，需要更新 `render.yaml`（加 `runtime: docker` 或改用 `dockerfilePath`）並重新走一次 Blueprint 設定，屆時記得同步更新本指令。
