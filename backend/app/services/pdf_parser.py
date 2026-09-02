import io
from dataclasses import dataclass

import pdfplumber


class PDFParsingError(Exception):
    pass


@dataclass
class PageText:
    page_number: int
    text: str


def extract_pdf_pages(file_bytes: bytes) -> list[PageText]:
    try:
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            pages = [
                PageText(page_number=i, text=page.extract_text() or "")
                for i, page in enumerate(pdf.pages, start=1)
            ]
    except Exception as exc:
        raise PDFParsingError(f"pdfplumber 無法開啟或解析 PDF: {exc}") from exc

    if not pages or not any(page.text.strip() for page in pages):
        raise PDFParsingError("PDF 未抽出任何文字內容（可能為掃描檔或加密檔），觸發 fallback")

    return pages
