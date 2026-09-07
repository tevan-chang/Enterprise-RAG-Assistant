# 0005. XLSX Schema-First 儲存策略：結構化資料落地在 documents.xlsx_sheets

## Context

Day 8 Report Mode 需要 `compute_table_metric` tool 在查詢當下對 XLSX 表格做精確 pandas 運算（加總/平均/最小/最大/計數）。但既有解析管線（Day 4）只把 XLSX 轉成 chunk 化的 Markdown Table 文字存進 `document_chunks`，供語意檢索與 citation 用，並不保留原始 DataFrame；專案目前也沒有接 Supabase Storage，上傳的原始檔案二進位內容處理完就丟棄，`documents.file_path` 欄位從一開始就沒有被寫入過。

要讓 `compute_table_metric` 能拿到型態正確的表格資料重新運算，有三個選項：

1. **接 Supabase Storage**：保留原始檔案，運算時重新下載 + `pandas.read_excel`。架構上最完整，但需要新增 Storage bucket、上傳/下載流程，與目前「沒有 Storage」的架構脫節，屬於 roadmap 沒排的 Scope Creep。
2. **從 chunk 化的 Markdown 反推**：不用新增欄位，但 chunk 化過程（`xlsx_parser.format_cell`）已經把數值轉成字串（整數轉字串、`NaN` 轉空字串），型態資訊遺失；若 sheet 被切成多個 chunk，重組回完整表格還要處理 header 重複、chunk 邊界對齊，脆弱且容易在 `chunk_size` 調整時悄悄壞掉。
3. **額外欄位存結構化 JSON**：在 `pandas.DataFrame` 已經在記憶體內、型態完整的當下，直接序列化存起來，之後原樣還原。

## Decision

採用選項 3。`process_xlsx_document`（`backend/app/services/document_pipeline.py`）在 pandas 成功解析當下（**不含 LlamaParse fallback 路徑**），額外呼叫 `xlsx_parser.sheets_to_json()`——用 `df.to_json(orient="split", date_format="iso")` 序列化每個工作表——寫進新增的 `documents.xlsx_sheets` jsonb 欄位（`supabase/migrations/20260907050000_documents_xlsx_sheets_column.sql`）。

- `compute_table_metric`（`report_tools.py`）透過 `xlsx_parser.sheet_from_json()` 用同樣的 `orient="split"` 還原 DataFrame 後執行運算，不依賴原始檔案或 chunk 內容。
- `build_xlsx_schema_summary()`（Schema-First 摘要，供 LLM 決定要呼叫哪個 tool）也是從同一個 `xlsx_sheets` 欄位動態算出 Sheet 名/欄位名/型態/Top-3 Sample，不需要另外預先計算存表。

## Consequences

**取得的好處**：
- 不需要引入 Supabase Storage，維持專案目前「上傳檔案處理完即丟棄二進位」的簡單架構，符合 MVP 範疇。
- 型態保真（數值運算不會因為字串化而出錯或需要額外轉型判斷），比反推 Markdown chunk 可靠。
- 同一份 `xlsx_sheets` 資料同時支援 `compute_table_metric`（精確運算）與 `build_xlsx_schema_summary`（Token 優化摘要），沒有資料重複維護的問題。

**付出的代價**：
- `documents` table 多了一個可能不小的 jsonb 欄位，大型 XLSX（例如上萬列）會讓單一 row 明顯變胖；目前 MVP 測試規模（60+ 列）沒有問題，但若之後要處理大檔案，這個設計需要重新評估（例如改回 Storage 或限制列數／改用獨立表）。
- LlamaParse fallback 路徑（純文字）沒有結構化資料可存，這類文件的 `compute_table_metric` 呼叫一律會落入 `ColumnNotFoundError` 的結構化錯誤路徑——這是刻意行為（沒有結構化表格就不能做精確數值運算），但屬於已知限制，不是 bug。
- 只有解析成功當下寫入一次；`services/classification.py` 的 `on_file_reupload` 目前只處理分類鎖，沒有連動更新 `xlsx_sheets`，若同一份文件被覆蓋重傳，需要之後另外補上同步邏輯。
