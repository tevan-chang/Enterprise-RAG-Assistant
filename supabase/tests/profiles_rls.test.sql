-- File: supabase/tests/profiles_rls.test.sql
-- Run:    supabase test db
-- 驗證 public.profiles 的 RLS：本人可查自己 profile、查不到別人的、anon 全擋。
--
-- 額外好處：直接 insert into auth.users 會觸發 handle_new_user trigger，
-- 順便驗證 trigger 有把 app_metadata/user_metadata 正確同步進 profiles
-- （auth.users 除了 id/is_sso_user/is_anonymous 外都允許 NULL 或有預設值，
-- 純 SQL insert 不會像透過 GoTrue Auth API 那樣因欄位缺值而失敗）。
begin;
create extension if not exists pgtap with schema extensions;
select plan(5);

insert into auth.users (id, email, raw_app_meta_data, raw_user_meta_data)
values
  ('11111111-1111-1111-1111-111111111111', 'user-a@test.local',
   '{"tenant_id": "tenant_a", "role": "admin"}'::jsonb,
   '{"display_name": "User A", "department": "Legal"}'::jsonb),
  ('22222222-2222-2222-2222-222222222222', 'user-b@test.local',
   '{"tenant_id": "tenant_b", "role": "viewer"}'::jsonb,
   '{"display_name": "User B", "department": "Ops"}'::jsonb);

select results_eq(
  $$select tenant_id, role, department, display_name from public.profiles
    where id = '11111111-1111-1111-1111-111111111111'$$,
  $$values ('tenant_a', 'admin', 'Legal', 'User A')$$,
  'handle_new_user trigger: 新使用者建立後自動同步 profiles'
);

-- ============================================================
-- anon 完全無權限
-- ============================================================
set local role anon;
select throws_ok(
  $$select * from public.profiles$$,
  '42501', null,
  'anon: SELECT 被拒絕'
);

-- ============================================================
-- authenticated：只能查自己的 profile
-- ============================================================
set local role authenticated;
set local request.jwt.claims =
  '{"role": "authenticated", "sub": "11111111-1111-1111-1111-111111111111", "app_metadata": {"tenant_id": "tenant_a", "role": "admin"}}';

select results_eq(
  $$select display_name from public.profiles where id = '11111111-1111-1111-1111-111111111111'$$,
  array['User A'],
  'authenticated: 可查到自己的 profile'
);
select is_empty(
  $$select * from public.profiles where id = '22222222-2222-2222-2222-222222222222'$$,
  'authenticated: 查不到別人的 profile'
);
select is(
  (select count(*)::int from public.profiles),
  1,
  'authenticated: select * 只回傳自己這一筆（RLS 過濾掉別人的列，不是查詢條件過濾）'
);

select * from finish();
rollback;
