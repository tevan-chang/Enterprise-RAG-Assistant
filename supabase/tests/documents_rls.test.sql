-- File: supabase/tests/documents_rls.test.sql
-- Run:    supabase test db
-- 驗證 documents table 的 RLS：role（Admin/Editor/Viewer）× confidentiality
-- （public/internal/restricted）× tenant（同租戶/跨租戶）× CRUD 矩陣（見 docs/spec_v3.1.md §3.4）
--
-- 設計說明：依 spec §3.1 混合式分工，RLS policy 只認 tenant_id（硬邊界），
-- role/confidentiality 過濾留在 FastAPI Query 層。因此本檔沒有窮舉 3×3×2×4=72
-- 組合，而是分軸驗證：confidentiality 軸、role 軸各自不影響 RLS 判斷，
-- 再用一組角色（editor）完整跑過 4 種 CRUD，避免同一不變量被重複斷言。
begin;
create extension if not exists pgtap with schema extensions;
select plan(20);

-- 固定測試資料：tenant_a / tenant_b 各 3 種 confidentiality
insert into public.documents (tenant_id, file_name, confidentiality)
values
  ('tenant_a', 'a_public.pdf', 'public'),
  ('tenant_a', 'a_internal.pdf', 'internal'),
  ('tenant_a', 'a_restricted.pdf', 'restricted'),
  ('tenant_b', 'b_public.pdf', 'public'),
  ('tenant_b', 'b_internal.pdf', 'internal'),
  ('tenant_b', 'b_restricted.pdf', 'restricted');

-- ============================================================
-- Section A：anon 完全無權限（無 GRANT，CRUD 四種操作皆須被拒）
-- ============================================================
set local role anon;

select throws_ok(
  $$select * from public.documents$$,
  '42501', null,
  'anon: SELECT 被拒絕'
);
select throws_ok(
  $$insert into public.documents (tenant_id, file_name) values ('tenant_a', 'anon.pdf')$$,
  '42501', null,
  'anon: INSERT 被拒絕'
);
select throws_ok(
  $$update public.documents set file_name = 'x'$$,
  '42501', null,
  'anon: UPDATE 被拒絕'
);
select throws_ok(
  $$delete from public.documents$$,
  '42501', null,
  'anon: DELETE 被拒絕'
);

-- ============================================================
-- Section B：confidentiality 軸（role 固定 viewer，tenant_a 身分）
-- 驗證 RLS 對 public/internal/restricted 一視同仁：
-- 同租戶全部可見，跨租戶（含 restricted）全部不可見
-- ============================================================
set local role authenticated;
set local request.jwt.claims =
  '{"role": "authenticated", "app_metadata": {"tenant_id": "tenant_a", "user_role": "viewer"}}';

select is(
  (select count(*)::int from public.documents where tenant_id = 'tenant_a'),
  3,
  'confidentiality 軸: tenant_a viewer 可看到自己租戶全部 3 種機密等級'
);
select is_empty(
  $$select * from public.documents where tenant_id = 'tenant_b' and confidentiality = 'public'$$,
  'confidentiality 軸: tenant_b 的 public 文件對 tenant_a 不可見'
);
select is_empty(
  $$select * from public.documents where tenant_id = 'tenant_b' and confidentiality = 'internal'$$,
  'confidentiality 軸: tenant_b 的 internal 文件對 tenant_a 不可見'
);
select is_empty(
  $$select * from public.documents where tenant_id = 'tenant_b' and confidentiality = 'restricted'$$,
  'confidentiality 軸: tenant_b 的 restricted 文件對 tenant_a 不可見（即使明確篩選）'
);

-- ============================================================
-- Section C：role 軸（confidentiality 固定 internal，tenant_a 身分）
-- 驗證 RLS 對 Admin/Editor/Viewer 一視同仁，皆只受 tenant_id 約束
-- ============================================================
set local request.jwt.claims =
  '{"role": "authenticated", "app_metadata": {"tenant_id": "tenant_a", "user_role": "admin"}}';
select results_eq(
  $$select file_name from public.documents where tenant_id = 'tenant_a' and confidentiality = 'internal'$$,
  array['a_internal.pdf'],
  'role 軸: admin 可看到同租戶 internal 文件'
);
select is_empty(
  $$select * from public.documents where tenant_id = 'tenant_b' and confidentiality = 'internal'$$,
  'role 軸: admin 看不到跨租戶 internal 文件'
);

set local request.jwt.claims =
  '{"role": "authenticated", "app_metadata": {"tenant_id": "tenant_a", "user_role": "editor"}}';
select results_eq(
  $$select file_name from public.documents where tenant_id = 'tenant_a' and confidentiality = 'internal'$$,
  array['a_internal.pdf'],
  'role 軸: editor 可看到同租戶 internal 文件'
);
select is_empty(
  $$select * from public.documents where tenant_id = 'tenant_b' and confidentiality = 'internal'$$,
  'role 軸: editor 看不到跨租戶 internal 文件'
);

set local request.jwt.claims =
  '{"role": "authenticated", "app_metadata": {"tenant_id": "tenant_a", "user_role": "viewer"}}';
select results_eq(
  $$select file_name from public.documents where tenant_id = 'tenant_a' and confidentiality = 'internal'$$,
  array['a_internal.pdf'],
  'role 軸: viewer 可看到同租戶 internal 文件'
);
select is_empty(
  $$select * from public.documents where tenant_id = 'tenant_b' and confidentiality = 'internal'$$,
  'role 軸: viewer 看不到跨租戶 internal 文件'
);

-- ============================================================
-- Section D：CRUD 四種操作完整跑一輪（代表角色 editor + internal）
-- ============================================================
set local request.jwt.claims =
  '{"role": "authenticated", "app_metadata": {"tenant_id": "tenant_a", "user_role": "editor"}}';

select lives_ok(
  $$insert into public.documents (tenant_id, file_name, confidentiality)
    values ('tenant_a', 'editor_insert.pdf', 'internal')$$,
  'CRUD: editor 可以在自己租戶 INSERT'
);
select throws_ok(
  $$insert into public.documents (tenant_id, file_name, confidentiality)
    values ('tenant_b', 'editor_insert_cross.pdf', 'internal')$$,
  '42501', null,
  'CRUD: editor 無法 INSERT 到其他租戶（WITH CHECK 擋下）'
);
select results_eq(
  $$update public.documents set file_name = 'editor_update.pdf'
    where tenant_id = 'tenant_a' and file_name = 'editor_insert.pdf'
    returning file_name$$,
  array['editor_update.pdf'],
  'CRUD: editor 可以 UPDATE 自己租戶的文件'
);
select is_empty(
  $$update public.documents set file_name = 'hacked.pdf'
    where tenant_id = 'tenant_b' and file_name = 'b_internal.pdf'
    returning file_name$$,
  'CRUD: editor 對跨租戶文件 UPDATE 影響 0 筆'
);
select results_eq(
  $$delete from public.documents
    where tenant_id = 'tenant_a' and file_name = 'editor_update.pdf'
    returning file_name$$,
  array['editor_update.pdf'],
  'CRUD: editor 可以 DELETE 自己租戶的文件'
);
select is_empty(
  $$delete from public.documents
    where tenant_id = 'tenant_b' and file_name = 'b_internal.pdf'
    returning file_name$$,
  'CRUD: editor 對跨租戶文件 DELETE 影響 0 筆'
);

select * from finish();
rollback;
