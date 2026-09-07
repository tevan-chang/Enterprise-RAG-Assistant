-- Report Mode Schema-First Token 優化用（見 docs/spec_v3.1.md §2.4 / roadmap Day 8）：
-- XLSX 解析成功時，除了既有的 chunk 化 Markdown 內容外，額外把每個工作表的結構化資料
-- （欄位名 + 資料列，pandas `to_json(orient="split")` 格式）存成 jsonb，供 Report Mode
-- 的 `compute_table_metric` tool 之後還原成 DataFrame 做精確 pandas 運算，
-- 不需要重新讀取原始檔案（本專案未持久化上傳的原始檔案二進位內容）。
-- 僅 XLSX 成功走 pandas 解析路徑會填值；PDF 與 LlamaParse fallback 路徑維持 null。
alter table public.documents add column xlsx_sheets jsonb;
