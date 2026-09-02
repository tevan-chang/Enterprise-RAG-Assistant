-- Day 3：PDF 解析管線所需欄位/資料表（見 docs/spec_v3.1.md §2.1、§4.1）
--
-- 注意：processing_status 與既有的 classification_status 是兩個獨立欄位。
-- classification_status（pending_auto/auto_labeled/manually_verified）：雙軌分類鎖狀態機（§4.2）。
-- processing_status（parsing/chunking/embedding/completed/failed）：解析管線進度，
-- 供前端 Polling（§2.3）與 lifespan Zombie Task Health Check（§2.1）使用。

alter table public.documents
  add column processing_status text not null default 'parsing'
    check (processing_status in ('parsing', 'chunking', 'embedding', 'completed', 'failed'));

create index documents_processing_status_idx on public.documents (processing_status, updated_at);

-- document_chunks：pdfplumber/pandas 解析後的 chunk 儲存（PDF 用 page_number；
-- XLSX 的 sheet/cell range citation 於 Day 4 另補欄位，此處先保持 nullable）。
-- embedding 欄位在 Day 3 階段先保留 NULL，實際寫入延後到 embedding 生成流程接上為止。
create table public.document_chunks (
  id uuid primary key default gen_random_uuid(),
  document_id uuid not null references public.documents (id) on delete cascade,
  tenant_id text not null,
  chunk_index int not null,
  page_number int,
  content text not null,
  token_count int not null,
  embedding vector(1536),
  created_at timestamptz not null default now(),
  unique (document_id, chunk_index)
);

create index document_chunks_document_id_idx on public.document_chunks (document_id);
create index document_chunks_tenant_id_idx on public.document_chunks (tenant_id);

alter table public.document_chunks enable row level security;

-- 與 documents 表相同的隔離策略：anon 無權限；authenticated 僅受 RLS tenant_id 約束。
grant select, insert, update, delete on public.document_chunks to authenticated;

create policy "document_chunks_tenant_isolation" on public.document_chunks
  for all
  to authenticated
  using (tenant_id = (auth.jwt() -> 'app_metadata' ->> 'tenant_id'))
  with check (tenant_id = (auth.jwt() -> 'app_metadata' ->> 'tenant_id'));
