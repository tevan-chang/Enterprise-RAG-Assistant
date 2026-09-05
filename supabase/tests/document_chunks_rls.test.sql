-- File: supabase/tests/document_chunks_rls.test.sql
-- Run:    supabase test db
-- 驗證 document_chunks 的 RLS 沿用 documents 表相同的 tenant_id 硬邊界策略
-- （見 docs/spec_v3.1.md §3.1、Day 3 pgvector 表結構）。
-- 不重複 documents_rls.test.sql 的 role/confidentiality 軸驗證，
-- 因 document_chunks 沒有 confidentiality/role 相關欄位，只做 tenant isolation + CRUD。
begin;
create extension if not exists pgtap with schema extensions;
select plan(15);

-- 固定測試資料：先建 tenant_a / tenant_b 各一筆 document，再各掛兩個 chunk
insert into public.documents (id, tenant_id, file_name)
values
  ('11111111-1111-1111-1111-111111111111', 'tenant_a', 'a_doc.pdf'),
  ('22222222-2222-2222-2222-222222222222', 'tenant_b', 'b_doc.pdf');

insert into public.document_chunks (document_id, tenant_id, chunk_index, page_number, content, token_count)
values
  ('11111111-1111-1111-1111-111111111111', 'tenant_a', 0, 1, 'tenant_a chunk 0', 10),
  ('11111111-1111-1111-1111-111111111111', 'tenant_a', 1, 1, 'tenant_a chunk 1', 10),
  ('22222222-2222-2222-2222-222222222222', 'tenant_b', 0, 1, 'tenant_b chunk 0', 10);

-- ============================================================
-- Section A：anon 完全無權限
-- ============================================================
set local role anon;

select throws_ok(
  $$select * from public.document_chunks$$,
  '42501', null,
  'anon: SELECT 被拒絕'
);
select throws_ok(
  $$insert into public.document_chunks (document_id, tenant_id, chunk_index, content, token_count)
    values ('11111111-1111-1111-1111-111111111111', 'tenant_a', 99, 'x', 1)$$,
  '42501', null,
  'anon: INSERT 被拒絕'
);

-- ============================================================
-- Section B：tenant isolation（同租戶可見，跨租戶不可見）
-- ============================================================
set local role authenticated;
set local request.jwt.claims =
  '{"role": "authenticated", "app_metadata": {"tenant_id": "tenant_a", "role": "viewer"}}';

select is(
  (select count(*)::int from public.document_chunks where tenant_id = 'tenant_a'),
  2,
  'tenant_a 可看到自己租戶的 2 個 chunk'
);
select is_empty(
  $$select * from public.document_chunks where tenant_id = 'tenant_b'$$,
  'tenant_a 看不到 tenant_b 的 chunk'
);

-- ============================================================
-- Section C：CRUD（代表角色 editor）
-- ============================================================
select lives_ok(
  $$insert into public.document_chunks (document_id, tenant_id, chunk_index, page_number, content, token_count)
    values ('11111111-1111-1111-1111-111111111111', 'tenant_a', 2, 2, 'tenant_a chunk 2', 12)$$,
  'CRUD: tenant_a 可以在自己租戶 INSERT chunk'
);
select throws_ok(
  $$insert into public.document_chunks (document_id, tenant_id, chunk_index, content, token_count)
    values ('22222222-2222-2222-2222-222222222222', 'tenant_b', 1, 'cross tenant', 5)$$,
  '42501', null,
  'CRUD: tenant_a 無法 INSERT 到 tenant_b（WITH CHECK 擋下）'
);
select results_eq(
  $$update public.document_chunks set content = 'updated'
    where tenant_id = 'tenant_a' and chunk_index = 2
    returning content$$,
  array['updated'],
  'CRUD: tenant_a 可以 UPDATE 自己租戶的 chunk'
);
select is_empty(
  $$update public.document_chunks set content = 'hacked'
    where tenant_id = 'tenant_b'
    returning content$$,
  'CRUD: tenant_a 對 tenant_b 的 chunk UPDATE 影響 0 筆'
);
select results_eq(
  $$delete from public.document_chunks
    where tenant_id = 'tenant_a' and chunk_index = 2
    returning chunk_index$$,
  array[2],
  'CRUD: tenant_a 可以 DELETE 自己租戶的 chunk'
);

-- ============================================================
-- Section E：XLSX 欄位（sheet_name / cell_range，見 roadmap Day 4）
-- 驗證新欄位不繞過既有 tenant isolation 硬邊界，且允許 NULL（PDF chunk 不填這兩欄）
-- ============================================================
reset role;

insert into public.documents (id, tenant_id, file_name)
values ('33333333-3333-3333-3333-333333333333', 'tenant_a', 'a_report.xlsx');

insert into public.document_chunks
  (document_id, tenant_id, chunk_index, page_number, content, token_count, sheet_name, cell_range)
values
  ('33333333-3333-3333-3333-333333333333', 'tenant_a', 0, null, '| 月份 | 營收 |', 20, '營收明細', 'A2:E11');

select has_column('public', 'document_chunks', 'sheet_name', 'schema: document_chunks 有 sheet_name 欄位');
select has_column('public', 'document_chunks', 'cell_range', 'schema: document_chunks 有 cell_range 欄位');

set local role authenticated;
set local request.jwt.claims =
  '{"role": "authenticated", "app_metadata": {"tenant_id": "tenant_a", "role": "viewer"}}';

select results_eq(
  $$select sheet_name, cell_range from public.document_chunks
    where document_id = '33333333-3333-3333-3333-333333333333'$$,
  $$values ('營收明細', 'A2:E11')$$,
  'XLSX chunk: tenant_a 可讀到自己的 sheet_name/cell_range citation'
);
select is(
  (select page_number from public.document_chunks
     where document_id = '33333333-3333-3333-3333-333333333333'),
  null,
  'XLSX chunk: page_number 允許為 NULL（PDF/XLSX citation 欄位互斥）'
);

set local request.jwt.claims =
  '{"role": "authenticated", "app_metadata": {"tenant_id": "tenant_b", "role": "viewer"}}';

select is_empty(
  $$select * from public.document_chunks where document_id = '33333333-3333-3333-3333-333333333333'$$,
  'XLSX chunk: tenant_b 看不到 tenant_a 的 XLSX chunk（sheet_name/cell_range 不繞過 tenant isolation）'
);
select throws_ok(
  $$insert into public.document_chunks
      (document_id, tenant_id, chunk_index, sheet_name, cell_range, content, token_count)
    values ('33333333-3333-3333-3333-333333333333', 'tenant_a', 99, 'hack', 'A1:A1', 'x', 1)$$,
  '42501', null,
  'XLSX chunk: tenant_b 的 session 無法用 tenant_id=tenant_a 冒充寫入 XLSX chunk（WITH CHECK 擋下）'
);

select * from finish();
rollback;
