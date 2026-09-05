-- 從 auth.users 自動同步 public.profiles。tenant_id/role 只能來自 app_metadata
-- （管理員經 Supabase Studio / Admin API 設定，使用者無法自行修改）；department/
-- display_name 來自 user_metadata（單純顯示用資訊，非授權判斷依據）。
-- security definer + search_path = '' 是 Supabase 官方文件建議寫法，避免 search_path 被劫持。
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  insert into public.profiles (id, tenant_id, role, department, display_name)
  values (
    new.id,
    new.raw_app_meta_data ->> 'tenant_id',
    coalesce(new.raw_app_meta_data ->> 'role', 'viewer'),
    new.raw_user_meta_data ->> 'department',
    new.raw_user_meta_data ->> 'display_name'
  )
  on conflict (id) do update set
    tenant_id = excluded.tenant_id,
    role = excluded.role,
    department = excluded.department,
    display_name = excluded.display_name,
    updated_at = now();

  return new;
end;
$$;

-- 新使用者建立時同步一次
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- 管理員事後改 app_metadata/user_metadata 時（例如調整 tenant_id/role）保持 profiles 同步
create trigger on_auth_user_metadata_updated
  after update of raw_app_meta_data, raw_user_meta_data on auth.users
  for each row execute function public.handle_new_user();
