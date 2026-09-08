-- 補上查重複用的複合索引，對應 DocumentsRepository 兩個高頻查詢：
-- get_by_content_hash()：(tenant_id, file_content_hash)
-- get_by_file_name()：(tenant_id, file_name)
-- 原本只有 documents_tenant_id_idx（單欄），這兩個查詢在租戶文件數變多後
-- 會退化成全表掃描再過濾，見 docs/dev_roadmap_v3.1.md Day 9-10 Buffer 盤點。
create index documents_tenant_id_content_hash_idx
  on public.documents (tenant_id, file_content_hash);

create index documents_tenant_id_file_name_idx
  on public.documents (tenant_id, file_name);
