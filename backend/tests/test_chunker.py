import pytest

from app.services.chunker import chunk_pages
from app.services.pdf_parser import PageText


def test_empty_pages_returns_no_chunks():
    assert chunk_pages([]) == []


def test_short_text_produces_single_chunk():
    pages = [PageText(page_number=1, text="Hello world, this is a short document.")]
    chunks = chunk_pages(pages, chunk_size=500, overlap=100)

    assert len(chunks) == 1
    assert chunks[0].page_number == 1
    assert chunks[0].chunk_index == 0
    assert chunks[0].token_count > 0


def test_long_text_respects_chunk_size_and_overlap():
    # 產生遠超過 500 tokens 的內容，確認會切成多個 chunk
    text = "企業知識庫測試段落。" * 400
    pages = [PageText(page_number=1, text=text)]

    chunks = chunk_pages(pages, chunk_size=500, overlap=100)

    assert len(chunks) > 1
    for chunk in chunks[:-1]:
        assert chunk.token_count == 500
    assert chunks[-1].token_count <= 500

    # chunk_index 必須連續遞增
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))


def test_chunk_page_number_tracks_source_page():
    pages = [
        PageText(page_number=1, text="第一頁內容。" * 5),
        PageText(page_number=2, text="第二頁內容。" * 400),
    ]
    chunks = chunk_pages(pages, chunk_size=500, overlap=100)

    page_numbers = {c.page_number for c in chunks}
    assert page_numbers == {1, 2}
    # 第一個 chunk 一定從第 1 頁開始
    assert chunks[0].page_number == 1


def test_overlap_must_be_smaller_than_chunk_size():
    with pytest.raises(ValueError):
        chunk_pages([PageText(page_number=1, text="x")], chunk_size=100, overlap=100)
