-- tenant_id 跨租戶隔離（硬邊界，見 docs/spec_v3.1.md §3.1 / §3.4）
-- confidentiality 等業務規則過濾留在 FastAPI Query 層，不在此處實作。
alter table public.documents enable row level security;

-- api.auto_expose_new_tables 預設關閉，新表不自動對 anon/authenticated 開放，需手動 GRANT。
-- anon 不給任何權限（預設拒絕）；authenticated 的可見範圍完全交由下方 RLS policy 過濾。
grant select, insert, update, delete on public.documents to authenticated;

create policy "documents_tenant_isolation" on public.documents
  for all
  to authenticated
  using (tenant_id = (auth.jwt() -> 'app_metadata' ->> 'tenant_id'))
  with check (tenant_id = (auth.jwt() -> 'app_metadata' ->> 'tenant_id'));
