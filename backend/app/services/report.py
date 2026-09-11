import json
import logging
from functools import lru_cache

import sentry_sdk
from openai import AsyncOpenAI

from app.config import settings
from app.services.report_tools import (
    TOOL_DEFINITIONS,
    build_xlsx_schema_summary,
    compute_table_metric,
    query_documents,
)
from app.services.token_usage import record_usage

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT_TEMPLATE = (
    "你是企業內部的報告生成助理。你可以呼叫兩個工具：\n"
    "1. query_documents：檢索知識庫中的相關文件片段。\n"
    "2. compute_table_metric：對已解析的 XLSX 表格做精確數值運算（sum/average/min/max/count），"
    "並支援先用 filter_column/filter_value 篩選列，再用 group_by_column 依欄位分組統計——"
    "篩選與分組可以同時使用，一次呼叫就能完成「篩選後分組統計」，不需要分兩次呼叫。\n"
    "呼叫 compute_table_metric 時，document_id/sheet_name/column/filter_column/group_by_column "
    "只能使用下方「可用表格 Schema」列出的值，不可自行臆測或編造欄位名稱。若 Schema 摘要中沒有你"
    "需要的表格，改用 query_documents 檢索，或直接回答目前查無相關資料。\n"
    "compute_table_metric 支援 group_by_column（選填）：只要使用者的問題提到「依/按/每個/各」"
    "某個類別欄位分別統計（例如「各部門」「每位業務」「依月份」），就必須帶上 group_by_column，"
    "不要因為不確定就略過分組直接回答整體加總或說「不支援分組」——這個工具本來就支援分組，"
    "group_by_column 一樣只能填 Schema 摘要中實際存在的欄位名稱。範例：使用者問「各業務的業績"
    "加總分別是多少」，應呼叫 compute_table_metric(column=\"業績\", operation=\"sum\", "
    "group_by_column=\"業務\")，而不是只回傳全體加總。\n"
    "若問題需要先篩選再統計（例如「已成交的商機依產業別加總」），務必在同一次 compute_table_metric "
    "呼叫中一次帶齊 filter_column/filter_value/group_by_column，不要先呼叫一次篩選、再呼叫一次分組——"
    "整個對話最多兩輪，第一輪呼叫工具、第二輪收斂成最終回答，第二輪已經沒有工具可用，分兩次呼叫會導致"
    "第二個步驟永遠無法執行。\n"
    "若目前工具能力無法完整回答問題（例如需要三個以上條件依序篩選、或需要 filter_column/"
    "group_by_column 以外的邏輯），必須明確告知使用者「目前工具僅支援 OOO，無法計算 XXX」，"
    "絕對不可以寫出「接下來將計算...」「我將為您統計...」這類承諾了卻沒有實際執行運算的句子，"
    "只描述已經確實做完的事。\n"
    "所有數值結論都必須來自 compute_table_metric 的實際運算結果，不可自行心算或估計。\n\n"
    "可用表格 Schema：\n{schema_summary}"
)


@lru_cache
def _get_client() -> AsyncOpenAI:
    return AsyncOpenAI(api_key=settings.openai_api_key)


def _build_system_prompt(tenant_id: str, role: str) -> str:
    schema_summary = build_xlsx_schema_summary(tenant_id, role)
    schema_text = (
        json.dumps(schema_summary, ensure_ascii=False) if schema_summary else "（本租戶目前沒有已解析的 XLSX 表格）"
    )
    return _SYSTEM_PROMPT_TEMPLATE.format(schema_summary=schema_text)


async def _dispatch_tool_call(tool_call, tenant_id: str, role: str, departments: list[str] | None = None) -> dict:
    try:
        args = json.loads(tool_call.function.arguments or "{}")
    except json.JSONDecodeError as exc:
        return {"status": "error", "error_type": "InvalidToolArguments", "message": str(exc)}

    if tool_call.function.name == "query_documents":
        results = await query_documents(
            query=args.get("query", ""),
            tenant_id=tenant_id,
            role=role,
            top_k=args.get("top_k") or 3,
            departments=departments,
        )
        return {"status": "success", "result": results}

    if tool_call.function.name == "compute_table_metric":
        result = await compute_table_metric(
            tenant_id=tenant_id,
            document_id=args.get("document_id", ""),
            sheet_name=args.get("sheet_name", ""),
            column=args.get("column", ""),
            operation=args.get("operation", ""),
            group_by_column=args.get("group_by_column"),
            filter_column=args.get("filter_column"),
            filter_value=args.get("filter_value"),
            top_n=args.get("top_n") or 5,
        )
        if result.get("status") == "error":
            # tool call 失敗路徑（見 spec §2.5 Observability）：結構化錯誤已回給 LLM 繼續組報告，
            # 這裡另外送 Sentry 一份，讓非預期的欄位/型態問題也能被追蹤到。
            sentry_sdk.capture_message(f"compute_table_metric 失敗: args={args} result={result}", level="warning")
        return result

    sentry_sdk.capture_message(f"Report Mode 收到未知 tool call: {tool_call.function.name}", level="warning")
    return {"status": "error", "error_type": "UnknownTool", "message": f"未知的 tool：{tool_call.function.name}"}


async def run_report_tool_calling(
    query: str, tenant_id: str, role: str, user_id: str, departments: list[str] | None = None
) -> dict:
    """Report Mode bounded tool-calling（見 spec §2.4 / CLAUDE.md Guardrail #5）：固定最多兩輪
    OpenAI 呼叫——第一輪決定要不要呼叫工具（可能同時呼叫多個），第二輪把工具結果收斂成最終回答，
    不做第二輪之後的追問或 reflection。`/api/reports/generate`（roadmap Day 9）直接呼叫本函式。

    tenant_id/role/departments 一律由呼叫端（已驗證的 request context）注入，不對 LLM 開放
    這三個參數（比照 chat.py 的 departments 轉發邏輯，見 CLAUDE.md 雙層權限隔離）。

    回傳 `{"content": <最終回答文字>, "tool_calls": [<實際執行的 tool call 記錄>]}`，
    tool_calls 供之後（Day 9）前端做 tool-calling 過程可視化用。
    """
    client = _get_client()
    messages: list[dict] = [
        {"role": "system", "content": _build_system_prompt(tenant_id, role)},
        {"role": "user", "content": query},
    ]

    response = await client.chat.completions.create(
        model=settings.chat_model,
        messages=messages,
        tools=TOOL_DEFINITIONS,
        tool_choice="auto",
    )
    message = response.choices[0].message
    tool_calls = message.tool_calls or []

    if not tool_calls:
        record_usage(
            tenant_id=tenant_id,
            user_id=user_id,
            feature="report",
            model=settings.chat_model,
            prompt_tokens=response.usage.prompt_tokens,
            completion_tokens=response.usage.completion_tokens,
        )
        return {"content": message.content, "tool_calls": []}

    messages.append(
        {
            "role": "assistant",
            "content": message.content,
            "tool_calls": [tool_call.model_dump() for tool_call in tool_calls],
        }
    )

    executed = []
    for tool_call in tool_calls:
        result = await _dispatch_tool_call(tool_call, tenant_id=tenant_id, role=role, departments=departments)
        executed.append({"tool": tool_call.function.name, "arguments": tool_call.function.arguments, "result": result})
        messages.append(
            {
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": json.dumps(result, ensure_ascii=False),
            }
        )

    # 第二輪不帶 tools，杜絕模型再度觸發 tool call（見 CLAUDE.md Guardrail #5：bounded 1-2 輪）。
    final_response = await client.chat.completions.create(model=settings.chat_model, messages=messages)
    record_usage(
        tenant_id=tenant_id,
        user_id=user_id,
        feature="report",
        model=settings.chat_model,
        prompt_tokens=response.usage.prompt_tokens + final_response.usage.prompt_tokens,
        completion_tokens=response.usage.completion_tokens + final_response.usage.completion_tokens,
    )
    return {"content": final_response.choices[0].message.content, "tool_calls": executed}
