-- File: supabase/tests/token_usage_rls.test.sql
-- Run:    supabase test db
-- 驗證 token_usage 的 RLS 沿用 documents/document_chunks 相同的 tenant_id 硬邊界策略
-- （見 docs/spec_v3.1.md §3.1、§10 Demo 版計費）。只做 tenant isolation + CRUD，
-- 沒有 role/confidentiality 軸（token_usage 沒有這兩個欄位）。
begin;
create extension if not exists pgtap with schema extensions;
select plan(9);

insert into public.token_usage (tenant_id, user_id, feature, model, prompt_tokens, completion_tokens)
values
  ('tenant_a', 'user-1', 'chat', 'gpt-4o', 100, 50),
  ('tenant_a', 'user-1', 'embedding', 'text-embedding-3-small', 200, 0),
  ('tenant_b', 'user-2', 'chat', 'gpt-4o', 300, 150);

-- ============================================================
-- Section A：anon 完全無權限
-- ============================================================
set local role anon;

select throws_ok(
  $$select * from public.token_usage$$,
  '42501', null,
  'anon: SELECT 被拒絕'
);
select throws_ok(
  $$insert into public.token_usage (tenant_id, user_id, feature, model, prompt_tokens, completion_tokens)
    values ('tenant_a', 'user-1', 'chat', 'gpt-4o', 1, 1)$$,
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
  (select count(*)::int from public.token_usage where tenant_id = 'tenant_a'),
  2,
  'tenant_a 可看到自己租戶的 2 筆 token_usage'
);
select is_empty(
  $$select * from public.token_usage where tenant_id = 'tenant_b'$$,
  'tenant_a 看不到 tenant_b 的 token_usage'
);
select is(
  (select coalesce(sum(prompt_tokens), 0)::int from public.token_usage where tenant_id = 'tenant_a'),
  300,
  'tenant_a 的 prompt_tokens 加總正確（100 + 200）'
);

-- ============================================================
-- Section C：CRUD
-- ============================================================
select lives_ok(
  $$insert into public.token_usage (tenant_id, user_id, feature, model, prompt_tokens, completion_tokens)
    values ('tenant_a', 'user-1', 'report', 'gpt-4o', 10, 5)$$,
  'CRUD: tenant_a 可以在自己租戶 INSERT token_usage'
);
select throws_ok(
  $$insert into public.token_usage (tenant_id, user_id, feature, model, prompt_tokens, completion_tokens)
    values ('tenant_b', 'user-2', 'chat', 'gpt-4o', 1, 1)$$,
  '42501', null,
  'CRUD: tenant_a 無法 INSERT 到 tenant_b（WITH CHECK 擋下）'
);
select is_empty(
  $$update public.token_usage set prompt_tokens = 9999
    where tenant_id = 'tenant_b'
    returning prompt_tokens$$,
  'CRUD: tenant_a 對 tenant_b 的 token_usage UPDATE 影響 0 筆'
);
select results_eq(
  $$delete from public.token_usage
    where tenant_id = 'tenant_a' and feature = 'report'
    returning feature$$,
  array['report'],
  'CRUD: tenant_a 可以 DELETE 自己租戶的 token_usage'
);

select * from finish();
rollback;
