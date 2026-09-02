-- Day 4：XLSX 解析管線 citation 欄位補完（見 docs/spec_v3.1.md §2.1、§4.1）
--
-- 20260902090000 建立 document_chunks 時已預留：PDF 用 page_number，
-- XLSX 的 sheet/cell range citation 於此補上，維持 nullable（PDF chunk 不會填這兩欄）。
-- 純欄位新增，不變更既有 RLS policy（tenant_isolation 以 row 為單位，新增欄位不受影響）。

alter table public.document_chunks
  add column sheet_name text,
  add column cell_range text;
