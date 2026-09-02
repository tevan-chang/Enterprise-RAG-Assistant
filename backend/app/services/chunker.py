from dataclasses import dataclass

import tiktoken

from app.services.pdf_parser import PageText

_ENCODING = tiktoken.get_encoding("cl100k_base")


@dataclass
class Chunk:
    chunk_index: int
    page_number: int | None
    content: str
    token_count: int


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
