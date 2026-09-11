from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import tiktoken

from app.services.chunker import chunk_xlsx_sheets
from app.services.report_tools import (
    build_xlsx_schema_summary,
    compute_table_metric,
    query_documents,
)
from app.services.xlsx_parser import extract_xlsx_sheets, sheets_to_json

_MODULE = "app.services.report_tools"
_TEST_XLSX = Path(__file__).resolve().parents[2] / "docs" / "restricted_sales_pipeline_60rows.xlsx"
_ENCODING = tiktoken.get_encoding("cl100k_base")


def _doc(**overrides) -> dict:
    sheets = sheets_to_json(
        [
            _sheet_frame(
                "業績",
                pd.DataFrame(
                    {
                        "業務": ["王小明", "李小華", "陳大文"],
                        "業績 (NT$)": [120000, 80000, 200000],
                        "備註": ["達標", None, "超標"],
                    }
                ),
            )
        ]
    )
    doc = {
        "id": "doc-1",
        "tenant_id": "tenant_a",
        "file_name": "業績表.xlsx",
        "confidentiality": "internal",
        "xlsx_sheets": sheets,
    }
    doc.update(overrides)
    return doc


def _sheet_frame(name: str, dataframe: pd.DataFrame):
    from app.services.xlsx_parser import SheetFrame

    return SheetFrame(sheet_name=name, dataframe=dataframe)


async def test_compute_table_metric_sum_returns_success():
    documents_repo = MagicMock()
    documents_repo.get.return_value = _doc()

    result = await compute_table_metric(
        tenant_id="tenant_a",
        document_id="doc-1",
        sheet_name="業績",
        column="業績 (NT$)",
        operation="sum",
        documents_repo=documents_repo,
    )

    assert result == {"status": "success", "result": 400000.0}


async def test_compute_table_metric_count_ignores_non_numeric():
    documents_repo = MagicMock()
    documents_repo.get.return_value = _doc()

    result = await compute_table_metric(
        tenant_id="tenant_a",
        document_id="doc-1",
        sheet_name="業績",
        column="備註",
        operation="count",
        documents_repo=documents_repo,
    )

    assert result == {"status": "success", "result": 2}


async def test_compute_table_metric_unknown_column_returns_structured_error():
    documents_repo = MagicMock()
    documents_repo.get.return_value = _doc()

    result = await compute_table_metric(
        tenant_id="tenant_a",
        document_id="doc-1",
        sheet_name="業績",
        column="不存在的欄位",
        operation="sum",
        documents_repo=documents_repo,
    )

    assert result["status"] == "error"
    assert result["error_type"] == "ColumnNotFoundError"


async def test_compute_table_metric_non_numeric_column_returns_type_error():
    documents_repo = MagicMock()
    documents_repo.get.return_value = _doc()

    result = await compute_table_metric(
        tenant_id="tenant_a",
        document_id="doc-1",
        sheet_name="業績",
        column="業務",
        operation="sum",
        documents_repo=documents_repo,
    )

    assert result["status"] == "error"
    assert result["error_type"] == "TypeError"


async def test_compute_table_metric_cross_tenant_document_returns_structured_error():
    """tenant_id 不吻合視同找不到文件（防止 LLM 被誘導跨租戶運算），見雙層權限隔離設計。"""
    documents_repo = MagicMock()
    documents_repo.get.return_value = _doc(tenant_id="tenant_b")

    result = await compute_table_metric(
        tenant_id="tenant_a",
        document_id="doc-1",
        sheet_name="業績",
        column="業績 (NT$)",
        operation="sum",
        documents_repo=documents_repo,
    )

    assert result == {
        "status": "error",
        "error_type": "ColumnNotFoundError",
        "message": "找不到文件：doc-1",
    }


async def test_compute_table_metric_group_by_sum_returns_grouped_list():
    documents_repo = MagicMock()
    documents_repo.get.return_value = _doc()

    result = await compute_table_metric(
        tenant_id="tenant_a",
        document_id="doc-1",
        sheet_name="業績",
        column="業績 (NT$)",
        operation="sum",
        group_by_column="業務",
        documents_repo=documents_repo,
    )

    assert result == {
        "status": "success",
        "result": {
            "groups": [
                {"group": "陳大文", "value": 200000.0, "share": 0.5},
                {"group": "王小明", "value": 120000.0, "share": 0.3},
                {"group": "李小華", "value": 80000.0, "share": 0.2},
            ],
            "filter": None,
        },
    }


async def test_compute_table_metric_group_by_count_returns_grouped_list():
    documents_repo = MagicMock()
    documents_repo.get.return_value = _doc()

    result = await compute_table_metric(
        tenant_id="tenant_a",
        document_id="doc-1",
        sheet_name="業績",
        column="備註",
        operation="count",
        group_by_column="業務",
        documents_repo=documents_repo,
    )

    assert result == {
        "status": "success",
        "result": {
            "groups": [
                {"group": "王小明", "value": 1, "share": 0.5},
                {"group": "陳大文", "value": 1, "share": 0.5},
                {"group": "李小華", "value": 0, "share": 0.0},
            ],
            "filter": None,
        },
    }


async def test_compute_table_metric_filter_only_returns_flat_result():
    documents_repo = MagicMock()
    documents_repo.get.return_value = _doc()

    result = await compute_table_metric(
        tenant_id="tenant_a",
        document_id="doc-1",
        sheet_name="業績",
        column="業績 (NT$)",
        operation="sum",
        filter_column="業務",
        filter_value="王小明",
        documents_repo=documents_repo,
    )

    assert result == {"status": "success", "result": 120000.0}


async def test_compute_table_metric_filter_and_group_by_combined():
    documents_repo = MagicMock()
    documents_repo.get.return_value = _doc(
        xlsx_sheets=sheets_to_json(
            [
                _sheet_frame(
                    "業績",
                    pd.DataFrame(
                        {
                            "業務": ["王小明", "李小華", "陳大文", "王小明"],
                            "業績 (NT$)": [120000, 80000, 200000, 60000],
                            "商機階段": ["已成交", "已成交", "已成交", "初步接觸"],
                        }
                    ),
                )
            ]
        )
    )

    result = await compute_table_metric(
        tenant_id="tenant_a",
        document_id="doc-1",
        sheet_name="業績",
        column="業績 (NT$)",
        operation="sum",
        filter_column="商機階段",
        filter_value="已成交",
        group_by_column="業務",
        documents_repo=documents_repo,
    )

    assert result == {
        "status": "success",
        "result": {
            "groups": [
                {"group": "陳大文", "value": 200000.0, "share": 0.5},
                {"group": "王小明", "value": 120000.0, "share": 0.3},
                {"group": "李小華", "value": 80000.0, "share": 0.2},
            ],
            "filter": {"column": "商機階段", "value": "已成交"},
        },
    }


async def test_compute_table_metric_real_xlsx_filter_and_group_by_top_n():
    """用真實測試檔驗證篩選+分組組合（見 test_schema_first_summary_uses_far_fewer_tokens_than_full_table
    的相同讀檔方式），篩「商機階段=已成交」再依「產業別」加總「預估金額 (NT$)」。
    """
    sheets = extract_xlsx_sheets(_TEST_XLSX.read_bytes())
    documents_repo = MagicMock()
    documents_repo.get.return_value = {
        "id": "doc-real",
        "tenant_id": "tenant_a",
        "file_name": "restricted_sales_pipeline_60rows.xlsx",
        "xlsx_sheets": sheets_to_json(sheets),
    }

    result = await compute_table_metric(
        tenant_id="tenant_a",
        document_id="doc-real",
        sheet_name=sheets[0].sheet_name,
        column="預估金額 (NT$)",
        operation="sum",
        filter_column="商機階段",
        filter_value="已成交",
        group_by_column="產業別",
        documents_repo=documents_repo,
    )

    assert result == {
        "status": "success",
        "result": {
            "groups": [
                {"group": "製造", "value": 13490000.0, "share": 0.2765},
                {"group": "教育", "value": 12760000.0, "share": 0.2616},
                {"group": "金融", "value": 11520000.0, "share": 0.2362},
                {"group": "零售", "value": 11010000.0, "share": 0.2257},
            ],
            "filter": {"column": "商機階段", "value": "已成交"},
        },
    }
    assert round(sum(g["share"] for g in result["result"]["groups"]), 4) == 1.0


async def test_compute_table_metric_group_by_min_returns_type_error():
    documents_repo = MagicMock()
    documents_repo.get.return_value = _doc()

    result = await compute_table_metric(
        tenant_id="tenant_a",
        document_id="doc-1",
        sheet_name="業績",
        column="業績 (NT$)",
        operation="min",
        group_by_column="業務",
        documents_repo=documents_repo,
    )

    assert result["status"] == "error"
    assert result["error_type"] == "TypeError"


async def test_compute_table_metric_unknown_filter_column_returns_structured_error():
    documents_repo = MagicMock()
    documents_repo.get.return_value = _doc()

    result = await compute_table_metric(
        tenant_id="tenant_a",
        document_id="doc-1",
        sheet_name="業績",
        column="業績 (NT$)",
        operation="sum",
        filter_column="不存在的篩選欄位",
        filter_value="x",
        documents_repo=documents_repo,
    )

    assert result["status"] == "error"
    assert result["error_type"] == "ColumnNotFoundError"


async def test_compute_table_metric_unknown_group_by_column_returns_structured_error():
    documents_repo = MagicMock()
    documents_repo.get.return_value = _doc()

    result = await compute_table_metric(
        tenant_id="tenant_a",
        document_id="doc-1",
        sheet_name="業績",
        column="業績 (NT$)",
        operation="sum",
        group_by_column="不存在的分組欄位",
        documents_repo=documents_repo,
    )

    assert result["status"] == "error"
    assert result["error_type"] == "ColumnNotFoundError"


async def test_compute_table_metric_unsupported_operation_returns_type_error():
    documents_repo = MagicMock()
    documents_repo.get.return_value = _doc()

    result = await compute_table_metric(
        tenant_id="tenant_a",
        document_id="doc-1",
        sheet_name="業績",
        column="業績 (NT$)",
        operation="stddev",
        documents_repo=documents_repo,
    )

    assert result["status"] == "error"
    assert result["error_type"] == "TypeError"


async def test_query_documents_wraps_dense_retriever_and_formats_labels():
    retriever = MagicMock()
    retriever.retrieve = AsyncMock(
        return_value=[
            {
                "document_id": "doc-2",
                "file_name": "2026Q2.xlsx",
                "page_number": None,
                "sheet_name": "營收明細",
                "cell_range": "B2:D15",
                "content": "營收內容",
            }
        ]
    )

    results = await query_documents(query="營收多少", tenant_id="tenant_a", role="admin", retriever=retriever)

    assert results == [{"label": "2026Q2.xlsx，工作表：營收明細 B2:D15", "content": "營收內容"}]
    retriever.retrieve.assert_awaited_once_with(
        query="營收多少", tenant_id="tenant_a", top_k=3, role="admin", departments=None
    )


async def test_query_documents_forwards_departments_to_retriever():
    retriever = MagicMock()
    retriever.retrieve = AsyncMock(return_value=[])

    await query_documents(
        query="營收多少", tenant_id="tenant_a", role="editor", departments=["財務部"], retriever=retriever
    )

    retriever.retrieve.assert_awaited_once_with(
        query="營收多少", tenant_id="tenant_a", top_k=3, role="editor", departments=["財務部"]
    )


def test_build_xlsx_schema_summary_excludes_full_table():
    documents_repo = MagicMock()
    documents_repo.list_by_tenant.return_value = [_doc()]

    summary = build_xlsx_schema_summary("tenant_a", "admin", documents_repo=documents_repo)

    assert len(summary) == 1
    entry = summary[0]
    assert entry["document_id"] == "doc-1"
    assert entry["sheet_name"] == "業績"
    assert {c["name"] for c in entry["columns"]} == {"業務", "業績 (NT$)", "備註"}
    assert len(entry["sample_rows"]) == 3  # Top-3 sample，不是全表


def test_build_xlsx_schema_summary_viewer_excludes_restricted_documents():
    documents_repo = MagicMock()
    documents_repo.list_by_tenant.return_value = [_doc(confidentiality="restricted")]

    summary = build_xlsx_schema_summary("tenant_a", "viewer", documents_repo=documents_repo)

    assert summary == []


def test_build_xlsx_schema_summary_skips_documents_without_parsed_xlsx():
    documents_repo = MagicMock()
    documents_repo.list_by_tenant.return_value = [_doc(xlsx_sheets=None)]

    summary = build_xlsx_schema_summary("tenant_a", "admin", documents_repo=documents_repo)

    assert summary == []


def test_schema_first_summary_uses_far_fewer_tokens_than_full_table():
    """Day 8 DoD：用 50+ 列的測試 XLSX 驗證傳給 LLM 的 payload 只有 schema 摘要而非全表
    （見 roadmap Day 8），此處直接印 token 數對比。
    """
    import json

    file_bytes = _TEST_XLSX.read_bytes()
    sheets = extract_xlsx_sheets(file_bytes)
    assert sum(len(sheet.dataframe) for sheet in sheets) >= 50

    full_table_chunks = chunk_xlsx_sheets(sheets, chunk_size=100_000)  # 不切塊，取得完整表格文字
    full_table_text = "\n\n".join(chunk.content for chunk in full_table_chunks)
    full_table_tokens = len(_ENCODING.encode(full_table_text))

    documents_repo = MagicMock()
    documents_repo.list_by_tenant.return_value = [
        {
            "id": "doc-3",
            "file_name": "restricted_sales_pipeline_60rows.xlsx",
            "confidentiality": "internal",
            "xlsx_sheets": sheets_to_json(sheets),
        }
    ]
    summary = build_xlsx_schema_summary("tenant_a", "admin", documents_repo=documents_repo)
    schema_tokens = len(_ENCODING.encode(json.dumps(summary, ensure_ascii=False)))

    print(f"full_table_tokens={full_table_tokens} schema_tokens={schema_tokens}")
    assert schema_tokens < full_table_tokens * 0.2
