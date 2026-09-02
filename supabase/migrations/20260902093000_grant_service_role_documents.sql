-- service_role 雖然 rolbypassrls=true（略過 RLS），但 Postgres table-level GRANT
-- 與 RLS bypass 是兩件事：本地 Supabase 預設只給 service_role TRUNCATE/REFERENCES/
-- TRIGGER/MAINTAIN，不含 SELECT/INSERT/UPDATE/DELETE。後端 FastAPI 服務一律用
-- service role key 連線（見 backend/app/db.py），需比照 authenticated 補上明確 GRANT。
grant select, insert, update, delete on public.documents to service_role;
grant select, insert, update, delete on public.document_chunks to service_role;
