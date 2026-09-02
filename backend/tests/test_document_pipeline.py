from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd

from app.adapters.llamaparse_adapter import FallbackParsingError
from app.services.document_pipeline import process_pdf_document, process_xlsx_document
from app.services.pdf_parser import PageText, PDFParsingError
from app.services.xlsx_parser import SheetFrame, XLSXParsingError

_MODULE = "app.services.document_pipeline"


def _final_status(documents_repo: MagicMock) -> str:
    return documents_repo.update_status.call_args_list[-1].args[1]


async def test_process_pdf_document_triggers_fallback_on_parsing_error():
    with (
        patch(f"{_MODULE}.DocumentsRepository") as MockDocumentsRepo,
        patch(f"{_MODULE}.ChunksRepository") as MockChunksRepo,
        patch(f"{_MODULE}.extract_pdf_pages", side_effect=PDFParsingError("boom")) as mock_extract,
        patch(f"{_MODULE}.LlamaParseAdapter") as MockAdapter,
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
    ):
        documents_repo = MockDocumentsRepo.return_value
        MockAdapter.return_value.parse = AsyncMock()

        await process_xlsx_document("doc-2", "tenant_a", b"file-bytes", "a.xlsx")

        MockAdapter.return_value.parse.assert_not_awaited()
        assert _final_status(documents_repo) == "completed"


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
