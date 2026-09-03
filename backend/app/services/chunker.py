from dataclasses import dataclass

import tiktoken

from app.services.pdf_parser import PageText
from app.services.xlsx_parser import SheetFrame, column_letter, row_to_markdown_line

_ENCODING = tiktoken.get_encoding("cl100k_base")


@dataclass
class Chunk:
    chunk_index: int
    page_number: int | None
    content: str
    token_count: int
    sheet_name: str | None = None
    cell_range: str | None = None
    embedding: list[float] | None = None


def chunk_pages(pages: list[PageText], chunk_size: int = 500, overlap: int = 100) -> list[Chunk]:
    """500 tokens + 100 overlap 滑動視窗切塊（見 spec §2.1 / roadmap Day 3）。

    跨頁時 chunk 歸屬視窗第一個 token 所在頁碼，維持單一頁碼 citation。
    """
    if overlap >= chunk_size:
        raise ValueError("overlap 必須小於 chunk_size")

    token_page_pairs: list[tuple[int, int]] = [
        (token, page.page_number) for page in pages for token in _ENCODING.encode(page.text)
    ]
    if not token_page_pairs:
        return []

    stride = chunk_size - overlap
    total = len(token_page_pairs)
    chunks: list[Chunk] = []
    start = 0
    while start < total:
        window = token_page_pairs[start : start + chunk_size]
        tokens = [token for token, _ in window]
        text = _ENCODING.decode(tokens).strip()
        if text:
            chunks.append(
                Chunk(
                    chunk_index=len(chunks),
                    page_number=window[0][1],
                    content=text,
                    token_count=len(tokens),
                )
            )
        if start + chunk_size >= total:
            break
        start += stride

    return chunks


def chunk_xlsx_sheets(sheets: list[SheetFrame], chunk_size: int = 500) -> list[Chunk]:
    """依列數分批，每個 chunk 皆含表頭 + 一段連續資料列，維持 Markdown Table 結構完整。

    XLSX 每列是獨立記錄，不像 PDF 連續文字需要 overlap 維持語意連貫（見 roadmap Day 4），
    故此處僅做「不重疊」的列分批；cell_range 依實際涵蓋的資料列回推（標題固定佔第 1 列）。
    """
    chunks: list[Chunk] = []
    for sheet in sheets:
        df = sheet.dataframe
        last_col = column_letter(len(df.columns) - 1)
        header = [str(col) for col in df.columns]
        header_line = "| " + " | ".join(header) + " |"
        separator_line = "| " + " | ".join(["---"] * len(header)) + " |"
        header_tokens = len(_ENCODING.encode(f"{header_line}\n{separator_line}"))

        row_lines = [row_to_markdown_line(row) for row in df.itertuples(index=False)]
        row_tokens = [len(_ENCODING.encode(line)) for line in row_lines]

        budget = max(chunk_size - header_tokens, 1)
        start, total_rows = 0, len(row_lines)
        while start < total_rows:
            end, running = start, 0
            while end < total_rows:
                if running + row_tokens[end] > budget and end > start:
                    break
                running += row_tokens[end]
                end += 1
                if running >= budget:
                    break

            body = "\n".join(row_lines[start:end])
            chunks.append(
                Chunk(
                    chunk_index=len(chunks),
                    page_number=None,
                    content=f"{header_line}\n{separator_line}\n{body}",
                    token_count=header_tokens + running,
                    sheet_name=sheet.sheet_name,
                    cell_range=f"A{start + 2}:{last_col}{end + 1}",
                )
            )
            start = end

    return chunks


def chunk_plain_text(text: str, chunk_size: int = 500, overlap: int = 100) -> list[Chunk]:
    """供 fallback（LlamaParse 純文字/Markdown 結果）使用的通用切塊，不綁定頁碼/sheet citation。"""
    if overlap >= chunk_size:
        raise ValueError("overlap 必須小於 chunk_size")

    tokens = _ENCODING.encode(text)
    if not tokens:
        return []

    stride = chunk_size - overlap
    chunks: list[Chunk] = []
    start = 0
    while start < len(tokens):
        window = tokens[start : start + chunk_size]
        content = _ENCODING.decode(window).strip()
        if content:
            chunks.append(Chunk(chunk_index=len(chunks), page_number=None, content=content, token_count=len(window)))
        if start + chunk_size >= len(tokens):
            break
        start += stride

    return chunks
