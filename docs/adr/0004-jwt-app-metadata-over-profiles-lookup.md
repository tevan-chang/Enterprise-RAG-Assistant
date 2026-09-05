# 0004. 授權來源：JWT app_metadata（取代 profiles table 查詢）

## Context

Day 7.5 要把身分驗證從 `X-Tenant-Id`/`X-User-Role` header 信任機制換成真正的 Supabase Auth JWT。同一時間也新增了 `public.profiles` table（id/tenant_id/role/department/display_name），由 `handle_new_user` trigger 從 `auth.users` 自動同步，供 pgTAP 測試與未來管理介面使用。

這裡有一個容易混淆的分工問題：`documents`/`document_chunks` 的既有 RLS policy（見 ADR 之前的 migration）已經是檢查 `auth.jwt() -> 'app_metadata' ->> 'tenant_id'`，而不是 join `profiles` table。新增 `profiles` table 之後，很直覺會想順手把後端 FastAPI 層的 `get_current_user()` 也改成查 `profiles` table 取得 `tenant_id`/`role`（这是很多 Supabase 教學文章示範的標準模式），但這樣做會製造兩個問題：

1. 每個受保護的 API 請求都要多一次 DB round-trip 查 `profiles`，而 JWT payload 本身已經內建 `app_metadata`，解出來是純 CPU 運算、零額外 I/O。
2. 會出現兩個授權判斷依據並存但邏輯不同步的風險——RLS 走 JWT claim、FastAPI 層走 `profiles` table，若兩者資料來源出現時間差（例如 admin 剛改了 `app_metadata` 但 `profiles` trigger 還沒觸發完成），會出現「RLS 說可以但 API 層說不行」或反過來的不一致視窗。

## Decision

後端 `get_current_user()`（`backend/app/dependencies/auth.py`）只解 JWT 本身的 `app_metadata.tenant_id`/`app_metadata.role`，用 `SUPABASE_JWT_SECRET`（Legacy JWT Secret，HS256）驗證簽章，**不查詢 `profiles` table**。

`profiles` table 的角色定位明確限縮為：
- 正規化的使用者顯示資料（`display_name`、`department`），JWT payload 裡沒有這些欄位時的查詢來源（例如未來要做「顯示上傳者名稱」這類功能）
- pgTAP 測試資料（`profiles_rls.test.sql`）用真實資料列驗證 RLS，而不是憑空的 `request.jwt.claims` fixture
- 未來管理介面（例如「列出某租戶下所有使用者」）的查詢來源

`tenant_id`/`role` 只能透過 `auth.users.raw_app_meta_data`（管理員經 Supabase Studio / Admin API 設定）設定，`handle_new_user` trigger 只是把它鏡像進 `profiles`，不是反過來由 `profiles` 產生 JWT claim。

## Consequences

**取得的好處**：
- API 層授權判斷零額外 DB 查詢，效能與既有 RLS 機制（同樣走 JWT claim）完全對齊，兩者不會出現判斷依據不同步的視窗
- `profiles` table 的職責單純（顯示資料 + 測試資料），不會有人誤以為改 `profiles.role` 就能改變使用者權限，降低未來維護時的誤用風險
- pgTAP 測試因為有真實 `profiles` 資料列可用，斷言更貼近實際資料形狀，不只是驗證抽象 claim

**付出的代價**：
- `tenant_id`/`role` 綁死在 JWT 簽發當下的值，若 admin 事後改了 `app_metadata`，使用者要等 JWT 過期重新登入（或 refresh token 帶出新 claim）才會生效，不是即時的（`handle_new_user` 的 UPDATE trigger 只同步了 `profiles` 顯示資料，不會讓已簽發的 JWT 立刻失效）
- 因為刻意不查 `profiles`，`department` 欄位目前完全沒有被任何授權/過濾邏輯使用，只是存著；若之後真的要做「依部門過濾文件存取」，屆時才需要重新評估是否要讓 API 層也查 `profiles`
