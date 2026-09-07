from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd

from app.adapters.llamaparse_adapter import FallbackParsingError
from app.services.document_pipeline import process_pdf_document, process_xlsx_document
from app.services.pdf_parser import PageText, PDFParsingError
from app.services.xlsx_parser import SheetFrame, XLSXParsingError

_MODULE = "app.services.document_pipeline"


def _final_status(documents_repo: MagicMock) -> str:
    return documents_repo.update_status.call_args_list[-1].args[1]


def _mock_embed_texts():
    """回傳與輸入等長的假向量，避免測試打真實 OpenAI API（見 test_embeddings.py 才是驗證 embed_texts 本身）。"""
    return AsyncMock(side_effect=lambda texts: [[0.0] * 3 for _ in texts])


async def test_process_pdf_document_triggers_fallback_on_parsing_error():
    with (
        patch(f"{_MODULE}.DocumentsRepository") as MockDocumentsRepo,
        patch(f"{_MODULE}.ChunksRepository") as MockChunksRepo,
        patch(f"{_MODULE}.extract_pdf_pages", side_effect=PDFParsingError("boom")) as mock_extract,
        patch(f"{_MODULE}.LlamaParseAdapter") as MockAdapter,
        patch(f"{_MODULE}.embed_texts", new=_mock_embed_texts()),
    ):
        documents_repo, chunks_repo = MockDocumentsRepo.return_value, MockChunksRepo.return_value
        MockAdapter.return_value.parse = AsyncMock(return_value="fallback markdown content")

        await process_pdf_document("doc-1", "tenant_a", b"file-bytes", "a.pdf")

        mock_extract.assert_called_once_with(b"file-bytes")
        MockAdapter.return_value.parse.assert_awaited_once_with(b"file-bytes", "a.pdf")
        assert _final_status(documents_repo) == "completed"
        chunks_repo.bulk_insert.assert_called_once()
        inserted_chunks = chunks_repo.bulk_insert.call_args.args[2]
        assert any("fallback markdown content" in c.content for c in inserted_chunks)


async def test_process_pdf_document_skips_fallback_when_parsing_succeeds():
    with (
        patch(f"{_MODULE}.DocumentsRepository") as MockDocumentsRepo,
        patch(f"{_MODULE}.ChunksRepository") as MockChunksRepo,
        patch(
            f"{_MODULE}.extract_pdf_pages",
            return_value=[PageText(page_number=1, text="normal parsed text")],
        ),
        patch(f"{_MODULE}.LlamaParseAdapter") as MockAdapter,
        patch(f"{_MODULE}.embed_texts", new=_mock_embed_texts()),
    ):
        documents_repo = MockDocumentsRepo.return_value
        MockAdapter.return_value.parse = AsyncMock()

        await process_pdf_document("doc-1", "tenant_a", b"file-bytes", "a.pdf")

        MockAdapter.return_value.parse.assert_not_awaited()
        assert _final_status(documents_repo) == "completed"


async def test_process_pdf_document_marks_failed_when_fallback_also_fails():
    with (
        patch(f"{_MODULE}.DocumentsRepository") as MockDocumentsRepo,
        patch(f"{_MODULE}.ChunksRepository") as MockChunksRepo,
        patch(f"{_MODULE}.extract_pdf_pages", side_effect=PDFParsingError("boom")),
        patch(f"{_MODULE}.LlamaParseAdapter") as MockAdapter,
    ):
        documents_repo, chunks_repo = MockDocumentsRepo.return_value, MockChunksRepo.return_value
        MockAdapter.return_value.parse = AsyncMock(side_effect=FallbackParsingError("llamaparse down"))

        await process_pdf_document("doc-1", "tenant_a", b"file-bytes", "a.pdf")

        assert _final_status(documents_repo) == "failed"
        chunks_repo.bulk_insert.assert_not_called()


def _sheet_frame() -> SheetFrame:
    return SheetFrame(sheet_name="Sheet1", dataframe=pd.DataFrame({"A": [1, 2], "B": [3, 4]}))


async def test_process_xlsx_document_triggers_fallback_on_parsing_error():
    with (
        patch(f"{_MODULE}.DocumentsRepository") as MockDocumentsRepo,
        patch(f"{_MODULE}.ChunksRepository") as MockChunksRepo,
        patch(f"{_MODULE}.extract_xlsx_sheets", side_effect=XLSXParsingError("boom")) as mock_extract,
        patch(f"{_MODULE}.LlamaParseAdapter") as MockAdapter,
        patch(f"{_MODULE}.embed_texts", new=_mock_embed_texts()),
    ):
        documents_repo, chunks_repo = MockDocumentsRepo.return_value, MockChunksRepo.return_value
        MockAdapter.return_value.parse = AsyncMock(return_value="fallback markdown content")

        await process_xlsx_document("doc-2", "tenant_a", b"file-bytes", "a.xlsx")

        mock_extract.assert_called_once_with(b"file-bytes")
        MockAdapter.return_value.parse.assert_awaited_once_with(b"file-bytes", "a.xlsx")
        assert _final_status(documents_repo) == "completed"
        chunks_repo.bulk_insert.assert_called_once()
        inserted_chunks = chunks_repo.bulk_insert.call_args.args[2]
        assert any("fallback markdown content" in c.content for c in inserted_chunks)


async def test_process_xlsx_document_skips_fallback_when_parsing_succeeds():
    with (
        patch(f"{_MODULE}.DocumentsRepository") as MockDocumentsRepo,
        patch(f"{_MODULE}.ChunksRepository") as MockChunksRepo,
        patch(f"{_MODULE}.extract_xlsx_sheets", return_value=[_sheet_frame()]),
        patch(f"{_MODULE}.LlamaParseAdapter") as MockAdapter,
        patch(f"{_MODULE}.embed_texts", new=_mock_embed_texts()),
    ):
        documents_repo = MockDocumentsRepo.return_value
        MockAdapter.return_value.parse = AsyncMock()

        await process_xlsx_document("doc-2", "tenant_a", b"file-bytes", "a.xlsx")

        MockAdapter.return_value.parse.assert_not_awaited()
        assert _final_status(documents_repo) == "completed"


async def test_process_xlsx_document_persists_structured_sheets_for_report_mode():
    """成功解析時要把結構化表格存進 documents.xlsx_sheets，供 Day 8 Report Mode 的
    compute_table_metric 還原 DataFrame 用；fallback 路徑（純文字）沒有結構化資料可存。
    """
    with (
        patch(f"{_MODULE}.DocumentsRepository") as MockDocumentsRepo,
        patch(f"{_MODULE}.ChunksRepository"),
        patch(f"{_MODULE}.extract_xlsx_sheets", return_value=[_sheet_frame()]),
        patch(f"{_MODULE}.LlamaParseAdapter"),
        patch(f"{_MODULE}.embed_texts", new=_mock_embed_texts()),
    ):
        documents_repo = MockDocumentsRepo.return_value

        await process_xlsx_document("doc-2", "tenant_a", b"file-bytes", "a.xlsx")

        documents_repo.update_xlsx_sheets.assert_called_once()
        doc_id, xlsx_sheets = documents_repo.update_xlsx_sheets.call_args.args
        assert doc_id == "doc-2"
        assert set(xlsx_sheets.keys()) == {"Sheet1"}
        assert xlsx_sheets["Sheet1"]["columns"] == ["A", "B"]
        assert xlsx_sheets["Sheet1"]["data"] == [[1, 3], [2, 4]]


async def test_process_xlsx_document_fallback_path_does_not_persist_structured_sheets():
    with (
        patch(f"{_MODULE}.DocumentsRepository") as MockDocumentsRepo,
        patch(f"{_MODULE}.ChunksRepository"),
        patch(f"{_MODULE}.extract_xlsx_sheets", side_effect=XLSXParsingError("boom")),
        patch(f"{_MODULE}.LlamaParseAdapter") as MockAdapter,
        patch(f"{_MODULE}.embed_texts", new=_mock_embed_texts()),
    ):
        documents_repo = MockDocumentsRepo.return_value
        MockAdapter.return_value.parse = AsyncMock(return_value="fallback markdown content")

        await process_xlsx_document("doc-2", "tenant_a", b"file-bytes", "a.xlsx")

        documents_repo.update_xlsx_sheets.assert_not_called()


async def test_process_xlsx_document_marks_failed_when_fallback_also_fails():
    with (
        patch(f"{_MODULE}.DocumentsRepository") as MockDocumentsRepo,
        patch(f"{_MODULE}.ChunksRepository") as MockChunksRepo,
        patch(f"{_MODULE}.extract_xlsx_sheets", side_effect=XLSXParsingError("boom")),
        patch(f"{_MODULE}.LlamaParseAdapter") as MockAdapter,
    ):
        documents_repo, chunks_repo = MockDocumentsRepo.return_value, MockChunksRepo.return_value
        MockAdapter.return_value.parse = AsyncMock(side_effect=FallbackParsingError("llamaparse down"))

        await process_xlsx_document("doc-2", "tenant_a", b"file-bytes", "a.xlsx")

        assert _final_status(documents_repo) == "failed"
        chunks_repo.bulk_insert.assert_not_called()
