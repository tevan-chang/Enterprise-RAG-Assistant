-- Day 5：DenseRetriever 用的 pgvector 語意檢索 RPC（見 docs/spec_v3.1.md §2.2）
--
-- 語法核對 Supabase 官方文件（Context7 guardrail，見 CLAUDE.md §3）：cosine 距離
-- 用 `<=>` 運算子，similarity = 1 - distance；filter 條件塞進 SQL function 內部，
-- 讓 planner 能與向量排序一起最佳化（若在呼叫端用 .eq() 事後過濾，filter 會在
-- ORDER BY + LIMIT 之後才套用，可能篩掉本該排進 top-k 的結果）。
--
-- Metadata Filter 兩段式（見 spec §2.2 設計）：
--   1. tenant_id 為必要條件（硬邊界，呼應 RLS tenant isolation）
--   2. departments / confidentiality 為可選條件，NULL 代表不過濾該軸
create or replace function public.match_document_chunks(
  query_embedding vector(1536),
  match_tenant_id text,
  match_count int default 5,
  filter_departments text[] default null,
  filter_confidentiality text[] default null
)
returns table (
  chunk_id uuid,
  document_id uuid,
  file_name text,
  page_number int,
  sheet_name text,
  cell_range text,
  content text,
  similarity float
)
language sql
stable
as $$
  select
    c.id as chunk_id,
    c.document_id,
    d.file_name,
    c.page_number,
    c.sheet_name,
    c.cell_range,
    c.content,
    1 - (c.embedding <=> query_embedding) as similarity
  from public.document_chunks c
  join public.documents d on d.id = c.document_id
  where c.tenant_id = match_tenant_id
    and c.embedding is not null
    and (filter_departments is null or d.departments && filter_departments)
    and (filter_confidentiality is null or d.confidentiality = any (filter_confidentiality))
  order by c.embedding <=> query_embedding asc
  limit least(match_count, 200);
$$;

-- function 預設 SECURITY INVOKER：後端一律用 service_role key 呼叫（見 backend/app/db.py），
-- service_role bypass RLS，故不需要 SECURITY DEFINER。
grant execute on function public.match_document_chunks to service_role;

-- ivfflat：MVP 資料量小，先用 lists=100 起步，未來資料量成長可依 pgvector 官方建議調整
-- （lists ≈ rows/1000）或改用 HNSW，不在本次 migration 範疇內。
create index document_chunks_embedding_idx on public.document_chunks
  using ivfflat (embedding vector_cosine_ops)
  with (lists = 100);
