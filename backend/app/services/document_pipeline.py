import logging

from app.adapters.llamaparse_adapter import FallbackParsingError, LlamaParseAdapter
from app.config import settings
from app.repositories.chunks_repository import ChunksRepository
from app.repositories.documents_repository import DocumentsRepository
from app.services.chunker import chunk_pages
from app.services.pdf_parser import PageText, PDFParsingError, extract_pdf_pages

logger = logging.getLogger(__name__)


async def process_pdf_document(document_id: str, tenant_id: str, file_bytes: bytes, file_name: str) -> None:
    """BackgroundTasks 派發的 in-process pipeline：parsing → chunking → completed/failed。

    純函式風格（不依賴外部 worker 狀態），未來若要轉移到 Celery/SQS 可直接複用
    （設計理由見 docs/adr/0002-backgroundtasks-over-celery.md）。
    """
    documents_repo = DocumentsRepository()
    chunks_repo = ChunksRepository()

    try:
        try:
            pages = extract_pdf_pages(file_bytes)
        except PDFParsingError as exc:
            logger.warning("pdfplumber 解析失敗，觸發 LlamaParse fallback: doc=%s err=%s", document_id, exc)
            fallback_text = await LlamaParseAdapter().parse(file_bytes, file_name)
            pages = [PageText(page_number=1, text=fallback_text)]

        documents_repo.update_status(document_id, "chunking")
        chunks = chunk_pages(pages, settings.chunk_size_tokens, settings.chunk_overlap_tokens)
        chunks_repo.bulk_insert(document_id, tenant_id, chunks)

        documents_repo.update_status(document_id, "completed")
    except (PDFParsingError, FallbackParsingError) as exc:
        logger.error("文件解析失敗（含 fallback）: doc=%s err=%s", document_id, exc)
        documents_repo.update_status(document_id, "failed")
    except Exception:
        logger.exception("文件處理管線發生未預期錯誤: doc=%s", document_id)
        documents_repo.update_status(document_id, "failed")
