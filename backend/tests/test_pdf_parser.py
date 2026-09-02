from pathlib import Path

import pytest

from app.services.pdf_parser import PDFParsingError, extract_pdf_pages

_TEST_PDF = Path(__file__).resolve().parents[2] / "docs" / "test_document.pdf"


def test_extract_pdf_pages_returns_page_numbered_text():
    file_bytes = _TEST_PDF.read_bytes()

    pages = extract_pdf_pages(file_bytes)

    assert len(pages) >= 1
    assert pages[0].page_number == 1
    assert any(page.text.strip() for page in pages)


def test_extract_pdf_pages_raises_on_garbage_input():
    with pytest.raises(PDFParsingError):
        extract_pdf_pages(b"not a real pdf")
