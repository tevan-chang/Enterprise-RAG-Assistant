"""驗證 LLAMA_CLOUD_API_KEY 補上後，fallback 真的能打通真實 LlamaParse API。

會發出真實網路請求（消耗 LlamaParse 額度），故用 skipif 保護：
沒有設定 LLAMA_CLOUD_API_KEY 的環境（例如 CI）會自動略過，不影響既有 mock 測試套件。
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import settings
from app.adapters.llamaparse_adapter import LlamaParseAdapter
from app.services.document_pipeline import process_pdf_document
from app.services.pdf_parser import PDFParsingError

pytestmark = pytest.mark.skipif(
    not settings.llama_cloud_api_key,
    reason="LLAMA_CLOUD_API_KEY 未設定，略過真實 API 呼叫測試",
)

_TEST_PDF = Path(__file__).resolve().parents[2] / "docs" / "test_document.pdf"
_MODULE = "app.services.document_pipeline"


async def test_llamaparse_adapter_parses_real_pdf_via_live_api():
    file_bytes = _TEST_PDF.read_bytes()

    result = await LlamaParseAdapter().parse(file_bytes, "test_document.pdf")

    assert isinstance(result, str)
    assert result.strip()


async def test_process_pdf_document_completes_via_real_llamaparse_fallback():
    """只驗證 LlamaParse fallback 這段真實 API；embedding 仍 mock 掉，
    避免這支測試同時依賴 OPENAI_API_KEY（不在本測試 scope 內）。
    """
    file_bytes = _TEST_PDF.read_bytes()

    with (
        patch(f"{_MODULE}.DocumentsRepository") as MockDocumentsRepo,
        patch(f"{_MODULE}.ChunksRepository") as MockChunksRepo,
        patch(f"{_MODULE}.extract_pdf_pages", side_effect=PDFParsingError("模擬原生解析異常")),
        patch(f"{_MODULE}.embed_texts", new=AsyncMock(side_effect=lambda texts: [[0.0] * 3 for _ in texts])),
    ):
        documents_repo = MockDocumentsRepo.return_value
        chunks_repo = MockChunksRepo.return_value

        await process_pdf_document("doc-live-1", "tenant_a", file_bytes, "test_document.pdf")

        final_status = documents_repo.update_status.call_args_list[-1].args[1]
        assert final_status == "completed"
        chunks_repo.bulk_insert.assert_called_once()
        inserted_chunks = chunks_repo.bulk_insert.call_args.args[2]
        assert inserted_chunks
        assert all(c.content.strip() for c in inserted_chunks)
