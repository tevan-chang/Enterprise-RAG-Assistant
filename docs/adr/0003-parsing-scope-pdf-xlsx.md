# 0003. 文件解析範疇：收斂為 PDF + XLSX（暫停 PPTX/DOCX）

## Context

企業知識庫常見文件格式包含 PDF、XLSX、PPTX、DOCX 四種。原規劃可能四種格式都支援原生解析，但多格式解析的邊際成本主要落在 edge case 處理（版面配置、圖表/文字混排、多層級表格等），不是核心 pipeline 邏輯，容易侵蝕 2 週單人開發時程中用來打磨核心功能（Chat/Citation/Report Mode）的時間（見 spec §11「多格式解析範疇過大排擠核心時程」風險項）。

## Decision

文件解析主線收斂為 PDF + XLSX 兩種格式：

- PDF 走 `pdf_parser.py`（`pdfplumber`），負責非結構化文本抽取 + 頁碼 metadata，對應 Citation 「頁碼跳轉」的展示需求
- XLSX 走 `xlsx_parser.py`（`pandas`），負責結構化表格轉換 + sheet/cell range metadata，對應 Report Mode「表格運算 Tool-calling」與 Citation「sheet+cell range 跳轉」的展示需求
- 兩條 pipeline 任一解析失敗，一律 fallback 到 `LlamaParseAdapter`（`services/document_pipeline.py` 共用尾段收斂至 `_embed_and_store_chunks`），不在應用層自行處理解析異常的 edge case
- PPTX/DOCX **不生成任何解析程式碼**（CLAUDE.md §2 Guardrail #4 明確禁止），Parser 走 Adapter 設計，未來若要擴充，新增一個 Adapter 實作即可，不影響現有架構

## Consequences

**取得的好處**：
- PDF 涵蓋「非結構化文本 Citation」、XLSX 涵蓋「結構化表格運算」，兩者已完整覆蓋本專案兩大技術亮點（Chat 引用跳轉、Report Mode 表格運算），不需要四種格式才能展示核心能力
- 省下的時間可以投入核心路徑（Chat SSE、Citation、Report Mode Tool-calling）的打磨，而不是分散在多格式 edge case
- Adapter Pattern 保留擴充彈性：未來要支援 PPTX/DOCX，只需新增對應 parser 並掛進 `_PIPELINE_BY_CONTENT_TYPE`，不需重構既有 pipeline

**付出的代價**：
- 上傳 PPTX/DOCX 目前會直接被 `POST /api/documents/upload` 以 422 拒絕（見 `routers/documents.py` 的 `_PIPELINE_BY_CONTENT_TYPE` 判斷），對於這兩種格式的企業文件無法納入知識庫，屬於已知且刻意接受的範疇限制
- 若未來真的要擴充支援，仍需要重新評估 PPTX（圖文混排、版面配置）與 DOCX（多層級標題結構）各自的 chunking 策略，不是直接複用現有 PDF/XLSX 邏輯就能涵蓋
