from pathlib import Path

import pytest

from app.services.chunker import chunk_xlsx_sheets
from app.services.xlsx_parser import XLSXParsingError, extract_xlsx_sheets

_TEST_XLSX = Path(__file__).resolve().parents[2] / "docs" / "test_report.xlsx"


def test_extract_xlsx_sheets_returns_non_empty_sheets():
    file_bytes = _TEST_XLSX.read_bytes()

    sheets = extract_xlsx_sheets(file_bytes)

    assert len(sheets) >= 1
    assert all(sheet.sheet_name for sheet in sheets)
    assert all(not sheet.dataframe.empty for sheet in sheets)


def test_extract_xlsx_sheets_raises_on_garbage_input():
    with pytest.raises(XLSXParsingError):
        extract_xlsx_sheets(b"not a real xlsx")


def test_chunk_xlsx_sheets_produces_sheet_and_cell_range_citation():
    file_bytes = _TEST_XLSX.read_bytes()
    sheets = extract_xlsx_sheets(file_bytes)

    chunks = chunk_xlsx_sheets(sheets)

    assert len(chunks) >= len(sheets)
    for chunk in chunks:
        assert chunk.sheet_name in {sheet.sheet_name for sheet in sheets}
        assert chunk.cell_range is not None
        assert chunk.page_number is None
        assert chunk.content.startswith("|")
        assert chunk.token_count > 0

    # chunk_index 必須連續遞增
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))


def test_chunk_xlsx_sheets_cell_range_starts_after_header_row():
    file_bytes = _TEST_XLSX.read_bytes()
    sheets = extract_xlsx_sheets(file_bytes)

    chunks = chunk_xlsx_sheets(sheets)

    first_chunk_by_sheet = {}
    for chunk in chunks:
        first_chunk_by_sheet.setdefault(chunk.sheet_name, chunk)

    for sheet in sheets:
        first_chunk = first_chunk_by_sheet[sheet.sheet_name]
        assert first_chunk.cell_range.startswith("A2:")


def test_chunk_xlsx_sheets_splits_large_sheet_across_chunks():
    file_bytes = _TEST_XLSX.read_bytes()
    sheets = extract_xlsx_sheets(file_bytes)

    # 用極小的 chunk_size 強迫每個 sheet 被切成多個 chunk，驗證分批不重疊
    chunks = chunk_xlsx_sheets(sheets, chunk_size=40)

    assert len(chunks) > len(sheets)
    ranges_by_sheet: dict[str, list[str]] = {}
    for chunk in chunks:
        ranges_by_sheet.setdefault(chunk.sheet_name, []).append(chunk.cell_range)

    for ranges in ranges_by_sheet.values():
        assert len(ranges) == len(set(ranges))
