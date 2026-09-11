# 0010. compute_table_metric 篩選 + 分組 + Top-N 收斂進單次 bounded tool call

## Context

Report Mode 是 bounded tool-calling（CLAUDE.md Guardrail #5）：固定最多兩輪 OpenAI 呼叫，第一輪決定要不要呼叫工具，第二輪不帶 `tools` 參數強制收斂成最終文字（`run_report_tool_calling`，`backend/app/services/report.py`）。`compute_table_metric`（`backend/app/services/report_tools.py`）原本只能對「單一 document + 單一 sheet + 單一 column」做一次全欄位聚合（sum/average/min/max/count），沒有「先篩選再分組」的能力。

實測發現具體案例：使用者問「統計目前成交占比最高的產業別，並加總預估金額」，這個問題本質上需要「先篩選商機階段=已成交，再依產業別分組加總」兩個依序步驟。因為工具只能做扁平單欄運算，LLM 想拆成兩次呼叫處理，但第二輪已經沒有工具可用（依 Guardrail #5 的 bounded 設計），導致：(1) 只能對全部階段的商機分組，忽略篩選條件，算出不符合問題原意的結果；(2) 回答斷在「接下來將計算...」這種承諾了卻沒有實際執行運算的句子。

要讓一次 tool call 就能處理「先篩選再統計」，有三個選項：

1. **放寬 bounded 輪數限制**：讓 LLM 可以多輪呼叫工具（先篩選、看結果、再分組）。直接違反 Guardrail #5「Tool-calling 一律 bounded（1-2 輪）」，等於把「多步規劃」的範疇打開，需要主動否決。
2. **開放任意運算表達式**：tool schema 接受一段 pandas query 字串或類 SQL 篩選條件，讓 LLM 自由組合任意邏輯。彈性最大，但等於在 tool 參數裡開一個可以執行任意運算邏輯的後門，違背 Schema-First 策略「document_id/sheet_name/column 只能從 Schema 摘要挑選具體值」的精神（見 0005），也難以做結構化錯誤處理與安全驗證。
3. **在既有五種運算之外，新增有限、明確列舉的 `filter_column`/`filter_value`/`group_by_column`/`top_n` 參數**，讓一次呼叫就能做完「篩選 + 分組」，所有新參數依然是從 Schema 摘要挑選的具體欄位名稱/數值，不開放任意運算式。

## Decision

採用選項 3。`compute_table_metric` 的 OpenAI function-calling schema（`TOOL_DEFINITIONS`）新增四個 optional 參數：`filter_column`/`filter_value`（先篩選列，兩者成對出現）、`group_by_column`（分組統計，僅 `sum`/`average`/`count` 支援——`min`/`max` 分組語意模糊，明確拋 `TypeError` 而非靜默允許）、`top_n`（分組結果只回傳前 N 名，1-10，預設 5）。`_run_pandas_operation` 依序處理：先套用 `filter_column`/`filter_value`（等值比對，轉字串後 `==`），再視 `group_by_column` 決定要不要分組；不分組時回傳型態與行為完全不變（純量 `int`/`float`），分組時回傳 `{"groups": [{"group","value","share"}], "filter": {...}|null}`（`share` 用**全體分組**加總當分母，避免 `top_n` 截斷後占比失真）。`_SYSTEM_PROMPT_TEMPLATE` 同步補上規則：要求 LLM 遇到「先篩選再統計」的問題時，必須在同一次呼叫帶齊三個參數，並且在工具能力不足以完整回答時（例如需要三個以上條件依序篩選）要明講限制，不可寫「接下來將計算...」這類承諾了卻沒有實際執行的句子。

## Consequences

**取得的好處**：
- 不需要放寬 Guardrail #5 的 bounded 1-2 輪限制，也不需要開放任意運算表達式——所有新參數依然是從 Schema 摘要挑選的具體字串，維持 Schema-First 策略「LLM 不可自行臆測欄位名稱」的護欄，複用既有的 `ColumnNotFoundError`/`TypeError` 結構化錯誤處理路徑，不需要另外設計新的驗證機制。
- 回傳結構清楚二分：不分組維持純量（向後相容既有直接呼叫端與測試），分組才是 `{groups, filter}` 結構，下游（LLM 收斂文字、前端 `ToolResultCell`）容易依型態分流渲染。
- 實測（含 Playwright 端到端驗證）證實：只要 system prompt 給出具體範例與明確指令，`tool_choice="auto"` 下 gpt-4o 能穩定在單次呼叫帶齊 `filter_column`/`filter_value`/`group_by_column`/`top_n`，不再需要分兩輪處理。

**付出的代價**：
- `filter_column`/`filter_value` 目前只支援「等於」比對，不支援範圍（大於/小於）或多條件 AND/OR；使用者問「金額大於 500 萬」這類範圍篩選仍然做不到，只能依賴 system prompt 規則讓 LLM 誠實告知「目前工具僅支援 OOO，無法計算 XXX」，而不是程式面直接支援。
- 分組結果格式（`{groups, filter}`）是針對本次需求設計的固定結構；若之後要再擴充（例如多條件篩選、多欄位分組），這個結構可能還要再變一次，屬於已知的技術債，屆時前端 `ToolResultCell` 與相關測試都要跟著同步調整（這次擴充就已經歷過一次：從最早的 flat dict 分組結果，改成含 `share`/`filter` 的結構化格式）。
- LLM 在 `tool_choice="auto"` 下是否穩定使用這些新參數，高度依賴 system prompt 的措辭與具體範例——開發過程中曾出現模型完全略過 `filter_column`、或宣稱「這個工具不支援分組」的情況，靠加強 prompt 的具體指令與範例才穩定下來，這是 prompt engineering 的脆弱面，沒有程式邏輯層級的保證，未來調整 system prompt 時需要重新做端到端驗證，不能只看單元測試通過就假設 LLM 行為不變。
