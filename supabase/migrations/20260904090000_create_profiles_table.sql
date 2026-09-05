-- profiles：對應 auth.users 的正規化使用者資料（tenant_id/role/department/display_name），
-- 由 handle_new_user trigger（見下一個 migration）從 auth.users 的 app_metadata/user_metadata
-- 自動同步。這張表不是 tenant/role 授權判斷的來源——documents/document_chunks 的 RLS 仍然是
-- 直接檢查 auth.jwt() -> 'app_metadata' ->> 'tenant_id'（見 20260901160100），這裡純粹是
-- 給 pgTAP 測試資料與之後管理介面用的正規化資料。
create table public.profiles (
  id uuid primary key references auth.users (id) on delete cascade,
  tenant_id text not null,
  role text not null,
  department text,
  display_name text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.profiles enable row level security;

-- api.auto_expose_new_tables 預設關閉，新表不自動對 anon/authenticated 開放，需手動 GRANT。
-- anon 不給任何權限（預設拒絕）；authenticated 只能查自己的 profile，交由下方 RLS policy 過濾。
grant select on public.profiles to authenticated;
grant select, insert, update, delete on public.profiles to service_role;
revoke all on public.profiles from anon;

create policy "profiles_select_own" on public.profiles
  for select
  to authenticated
  using (id = auth.uid());
