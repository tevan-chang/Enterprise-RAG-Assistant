-- 防禦性 migration：明確撤銷 anon 對 documents 的權限，並修正 schema 層級預設權限。
-- 起因：Supabase Cloud 專案可能帶有舊版「auto_expose_new_tables」預設權限
-- （在 public schema 對 anon 自動 GRANT 新表），本地 Docker 新版預設不會如此，
-- 兩邊行為不一致。此 migration 讓兩邊都明確以最小權限為準，不依賴任一邊的預設值。
revoke all on public.documents from anon;
alter default privileges in schema public revoke all on tables from anon;
