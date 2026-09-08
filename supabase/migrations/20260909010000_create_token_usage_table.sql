-- Day 9-10 Buffer 前補齊：Token 用量記錄（見 docs/spec_v3.1.md §10 Demo 版計費）。
-- 只做「累加 token 數 + 前端即時算 cost」，不做真實計費結算/月結週期/額度阻擋。
create table public.token_usage (
  id uuid primary key default gen_random_uuid(),
  tenant_id text not null,
  user_id text not null,
  feature text not null check (feature in ('chat', 'report', 'embedding', 'classification')),
  model text not null,
  prompt_tokens int not null default 0,
  completion_tokens int not null default 0,
  created_at timestamptz not null default now()
);

create index token_usage_tenant_id_idx on public.token_usage (tenant_id);

alter table public.token_usage enable row level security;

-- 與 documents/document_chunks 相同的隔離策略：anon 無權限；authenticated 僅受 RLS tenant_id 約束；
-- service_role 另外明確 GRANT（見 20260902093000_grant_service_role_documents.sql 的說明：
-- service_role 雖 bypass RLS，table-level GRANT 仍要另外給）。
grant select, insert, update, delete on public.token_usage to authenticated;
grant select, insert, update, delete on public.token_usage to service_role;

create policy "token_usage_tenant_isolation" on public.token_usage
  for all
  to authenticated
  using (tenant_id = (auth.jwt() -> 'app_metadata' ->> 'tenant_id'))
  with check (tenant_id = (auth.jwt() -> 'app_metadata' ->> 'tenant_id'));
