# 0011. Gmail OAuth consent screen 從 Testing 切到 Production，取代逐次重新授權

## Context

`GmailAPINotificationAdapter`（`backend/app/adapters/notifications.py`）用 `google.oauth2.credentials.Credentials` 搭配存在環境變數的長效 `refresh_token`（`backend/app/config.py` 的 `gmail_oauth_client_id`／`gmail_oauth_client_secret`／`gmail_oauth_refresh_token`）走離線授權，設計上不需要每次 runtime 互動式同意——一次性 OAuth consent 已在 GCP Console 完成。

但這組 `refresh_token` 每 7 天就會失效，導致 `send_notification()` 與健檢端點 `POST /api/v1/admin/test-notification` 開始拋 `NotificationError`。這件事已經真實發生過一次：Gmail API 的 `.execute()` 內部觸發 `Credentials.refresh()` 時丟出 `google.auth.exceptions.RefreshError("invalid_grant: Token has been expired or revoked.")`，因為當時程式碼只接了 `HttpError`，沒接 `RefreshError`，造成 500 直接洩漏給呼叫端（對應 Sentry issue RAG-ASSISTANT-B，回歸測試見 `backend/tests/test_notifications_adapter.py::test_send_wraps_refresh_error_as_notification_error`）。

排查後確認的根因，跟程式碼寫法、憑證讀取方式完全無關：**GCP 專案的 OAuth consent screen 只要 Publishing status 還停在 Testing，該專案核發出去的所有 refresh token（不論哪個 Google 帳號授權）一律 7 天強制過期**。原本補上 `RefreshError` 例外處理只是讓失敗「不洩漏成 500、改成乾淨的 502／log」，屬於治標；沒有解掉「每 7 天就要有人手動重新走一次 OAuth 同意流程」的根本問題。

考慮過的替代方案：改用 SMTP + App Password 寄信，可以完全繞開 OAuth refresh token 這整套機制。但 CLAUDE.md Guardrail #11 明確要求「Gmail API 發信一律用 `google-api-python-client`」，換成 SMTP 屬於明確違反 Guardrail 的方案，予以否決。

## Decision

把 GCP Console 的 OAuth consent screen Publishing status 從 **Testing** 改成 **In production**。這個狀態下核發的 refresh token 沒有 7 天強制過期限制（除非被使用者主動撤銷，或 6 個月完全沒被使用過）。

因為 `gmail.send` 屬於 Google 認定的 sensitive scope，切換到 Production 前，GCP 的 Branding 分頁要求填妥 App name／User support email／Developer contact information／Homepage URL／Privacy Policy URL，且後兩者網址網域必須列在 Authorized domains 內。為滿足這個必填條件，新增了 `frontend/app/privacy/page.tsx` 靜態隱私權政策頁面，並在 `frontend/middleware.ts` 的 `PUBLIC_PATHS` 加入 `/privacy`，讓這個路徑不需要登入即可存取（GCP 審核與一般使用者都要能直接看到）。

發布為 Production 後，consent 畫面會出現「這個應用程式未經 Google 驗證」的警告——這個警告只出現在走 OAuth 同意畫面的當下（一次性換發 refresh_token 那一次），不影響背景 API 呼叫本身，因此不需要真的送 Google 完整驗證審核。

## Consequences

**取得的好處**：
- 之後核發的 `refresh_token` 不會再有 7 天強制過期，不需要靠人工每週重新走一次 OAuth 同意流程來維持 Gmail 通知功能可用。
- 既有的 `RefreshError` 例外處理（`send_notification()` 吞掉並 log + Sentry、`test-notification` 端點刻意讓它冒出成 502）不需要改動，長效 token 只是讓這條錯誤路徑被觸發的頻率大幅降低，不是取代它——refresh token 被使用者手動撤銷、或憑證外洩後被 Google 強制吊銷，仍然會走到這條路徑，觀測機制照樣要留著。

**付出的代價**：
- 切換 Publishing status **只影響之後新核發的 refresh token**，狀態轉換前已經核發、目前寫在 `backend/.env`／根目錄 `.env`／Render 環境變數裡的那組 `gmail_oauth_refresh_token` 不會自動變長效，仍照原本的規則過期。要讓系統真正吃到長效 token，之後需要再手動走一次 OAuth 同意流程換發新 token，並同步更新這幾處環境變數——這是本次決策範圍外、後續要單獨處理的動作。
- `middleware.ts` 的 `PUBLIC_PATHS` 多了一個不需要登入即可存取的路徑。`/privacy` 頁面內容純靜態、不查詢任何租戶資料，風險可控，但往後任何人要在 `PUBLIC_PATHS` 加新路徑時，都要重新確認新增的頁面本身不會意外洩漏需要驗證才能看的資訊。
- Production 狀態下，一般使用者（非開發者本人）如果之後也要對這個 GCP 專案做 OAuth 授權，會看到「未驗證應用程式」警告畫面。目前使用情境只有專案管理者自己做一次性授權，可接受；如果未來要開放給其他外部使用者走這個 OAuth flow，需要重新評估是否要送 Google 的正式驗證審核。
