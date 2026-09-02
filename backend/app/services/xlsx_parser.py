import io
from dataclasses import dataclass

import pandas as pd


class XLSXParsingError(Exception):
    pass


@dataclass
class SheetFrame:
    sheet_name: str
    dataframe: pd.DataFrame


def extract_xlsx_sheets(file_bytes: bytes) -> list[SheetFrame]:
    try:
        raw_sheets = pd.read_excel(io.BytesIO(file_bytes), sheet_name=None, engine="openpyxl")
    except Exception as exc:
        raise XLSXParsingError(f"pandas 無法開啟或解析 XLSX: {exc}") from exc

    sheets = [SheetFrame(sheet_name=name, dataframe=df) for name, df in raw_sheets.items() if not df.empty]

    if not sheets:
        raise XLSXParsingError("XLSX 未抽出任何有效工作表內容（可能為空檔或格式異常），觸發 fallback")

    return sheets


def column_letter(index: int) -> str:
    """0-based 欄位索引 → Excel 欄位字母（0 → A, 25 → Z, 26 → AA ...）。"""
    letters = ""
    index += 1
    while index > 0:
        index, remainder = divmod(index - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def format_cell(value) -> str:
    if pd.isna(value):
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def row_to_markdown_line(row: tuple) -> str:
    return "| " + " | ".join(format_cell(v) for v in row) + " |"
