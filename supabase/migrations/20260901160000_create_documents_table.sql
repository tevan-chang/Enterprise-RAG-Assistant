-- documents table（見 docs/spec_v3.1.md §4.1 Document Metadata Schema）
create table public.documents (
  id uuid primary key default gen_random_uuid(),
  tenant_id text not null,
  file_name text not null,
  file_path text,
  departments text[] not null default '{}',
  auto_categories text[] not null default '{}',
  manual_categories text[] not null default '{}',
  final_categories text[] not null default '{}',
  classification_status text not null default 'pending_auto'
    check (classification_status in ('pending_auto', 'auto_labeled', 'manually_verified')),
  confidentiality text not null default 'internal'
    check (confidentiality in ('public', 'internal', 'restricted')),
  file_content_hash text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index documents_tenant_id_idx on public.documents (tenant_id);
