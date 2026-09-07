import pandas as pd

from app.adapters.retrievers import VIEWER_ALLOWED_CONFIDENTIALITY, DenseRetriever
from app.repositories.documents_repository import DocumentsRepository
from app.services.xlsx_parser import sheet_from_json

_SUPPORTED_OPERATIONS = {"sum", "average", "min", "max", "count"}

# Report Mode 兩個 bounded tool 的 OpenAI function-calling schema（見 spec §2.4 / roadmap Day 8）。
TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "query_documents",
            "description": "在租戶知識庫中做語意檢索，取得與問題相關的文件片段與出處標籤。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "檢索用的查詢字串"},
                    "top_k": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 5,
                        "description": "回傳筆數，預設 3",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compute_table_metric",
            "description": (
                "對已解析的 XLSX 表格做精確數值運算（sum/average/min/max/count）。"
                "document_id / sheet_name / column 必須從對話中提供的 Schema 摘要挑選，"
                "不可自行臆測欄位名稱或表格內容。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "document_id": {"type": "string", "description": "Schema 摘要中的 document_id"},
                    "sheet_name": {"type": "string", "description": "Schema 摘要中的 sheet_name"},
                    "column": {"type": "string", "description": "Schema 摘要中的欄位名稱"},
                    "operation": {"type": "string", "enum": sorted(_SUPPORTED_OPERATIONS)},
                },
                "required": ["document_id", "sheet_name", "column", "operation"],
            },
        },
    },
]


class ColumnNotFoundError(Exception):
    pass


def _format_chunk_label(chunk: dict) -> str:
    if chunk.get("sheet_name"):
        return f"{chunk['file_name']}，工作表：{chunk['sheet_name']} {chunk.get('cell_range') or ''}".strip()
    return f"{chunk['file_name']}，第 {chunk.get('page_number')} 頁"


async def query_documents(
    *,
    query: str,
    tenant_id: str,
    role: str,
    top_k: int = 3,
    departments: list[str] | None = None,
    retriever: DenseRetriever | None = None,
) -> list[dict]:
    """`query_documents` tool 實作：包裝既有 DenseRetriever（見 spec §2.4）。

    tenant_id/role/departments 一律由呼叫端（已驗證的 request context）注入，不對 LLM 開放
    這三個參數，避免 tool-calling 被誘導跨租戶檢索或繞過 department-scoped 過濾
    （比照 chat.py 的 departments 轉發邏輯）。
    """
    retriever = retriever or DenseRetriever()
    chunks = await retriever.retrieve(
        query=query, tenant_id=tenant_id, top_k=top_k, role=role, departments=departments
    )
    return [{"label": _format_chunk_label(chunk), "content": chunk["content"]} for chunk in chunks]


def _run_pandas_operation(
    tenant_id: str,
    document_id: str,
    sheet_name: str,
    column: str,
    operation: str,
    documents_repo: DocumentsRepository,
):
    if operation not in _SUPPORTED_OPERATIONS:
        raise TypeError(f"不支援的運算方式：{operation}（僅支援 {sorted(_SUPPORTED_OPERATIONS)}）")

    document = documents_repo.get(document_id)
    if document is None or document["tenant_id"] != tenant_id:
        raise ColumnNotFoundError(f"找不到文件：{document_id}")

    sheets = document.get("xlsx_sheets") or {}
    sheet_json = sheets.get(sheet_name)
    if sheet_json is None:
        raise ColumnNotFoundError(f"文件「{document['file_name']}」找不到工作表：{sheet_name}")

    df = sheet_from_json(sheet_json)
    if column not in df.columns:
        raise ColumnNotFoundError(f"工作表「{sheet_name}」找不到欄位：{column}")

    series = df[column]
    if operation == "count":
        return int(series.count())

    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.notna().sum() == 0:
        raise TypeError(f"欄位「{column}」無法轉換為數值，無法執行 {operation} 運算")

    if operation == "sum":
        return float(numeric.sum())
    if operation == "average":
        return float(numeric.mean())
    if operation == "min":
        return float(numeric.min())
    return float(numeric.max())


async def compute_table_metric(
    *,
    tenant_id: str,
    document_id: str,
    sheet_name: str,
    column: str,
    operation: str,
    documents_repo: DocumentsRepository | None = None,
) -> dict:
    """`compute_table_metric` tool 實作（見 spec §2.4 錯誤處理範例）：
    結構化 try/except，讓 tool-calling 失敗路徑也能回傳可讀訊息給 LLM 組報告，
    而不是讓整個 Report Mode 請求整條掛掉。
    """
    documents_repo = documents_repo or DocumentsRepository()
    try:
        result = _run_pandas_operation(tenant_id, document_id, sheet_name, column, operation, documents_repo)
        return {"status": "success", "result": result}
    except (ColumnNotFoundError, TypeError) as exc:
        return {"status": "error", "error_type": type(exc).__name__, "message": str(exc)}


def build_xlsx_schema_summary(tenant_id: str, role: str, documents_repo: DocumentsRepository | None = None) -> list[dict]:
    """XLSX Schema-First Strategy（見 spec §2.4 / roadmap Day 8）：組出「Sheet 名 + 欄位名 +
    型態 + Top-3 Sample」摘要放進 Report Mode system prompt，取代把整張表塞進 Context——
    LLM 依此摘要決定要對哪個 document_id/sheet_name/column 呼叫 `compute_table_metric`，
    實際運算交由後端 pandas 執行，避免大表格塞進 prompt 被截斷導致誤算。

    Viewer 比照 DenseRetriever 的 confidentiality 過濾（見 adapters/retrievers.py），
    排除 restricted 文件，避免 Schema 摘要（含欄位名/樣本列）洩漏機密表格內容。
    """
    documents_repo = documents_repo or DocumentsRepository()
    summary = []
    for doc in documents_repo.list_by_tenant(tenant_id):
        if role == "viewer" and doc["confidentiality"] not in VIEWER_ALLOWED_CONFIDENTIALITY:
            continue
        sheets = doc.get("xlsx_sheets") or {}
        for sheet_name, sheet_json in sheets.items():
            df = sheet_from_json(sheet_json)
            summary.append(
                {
                    "document_id": doc["id"],
                    "file_name": doc["file_name"],
                    "sheet_name": sheet_name,
                    "columns": [{"name": str(col), "dtype": str(df[col].dtype)} for col in df.columns],
                    "sample_rows": df.head(3).to_dict(orient="records"),
                }
            )
    return summary
