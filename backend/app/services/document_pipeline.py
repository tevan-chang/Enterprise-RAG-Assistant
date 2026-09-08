import logging

import sentry_sdk

from app.adapters.llamaparse_adapter import FallbackParsingError, LlamaParseAdapter
from app.config import settings
from app.repositories.chunks_repository import ChunksRepository
from app.repositories.documents_repository import DocumentsRepository
from app.services.classification import auto_classify
from app.services.chunker import Chunk, chunk_pages, chunk_plain_text, chunk_xlsx_sheets
from app.services.embeddings import EmbeddingError, embed_texts
from app.services.pdf_parser import PageText, PDFParsingError, extract_pdf_pages
from app.services.xlsx_parser import XLSXParsingError, extract_xlsx_sheets, sheets_to_json

logger = logging.getLogger(__name__)


async def _embed_and_store_chunks(
    document_id: str,
    tenant_id: str,
    user_id: str,
    file_name: str,
    chunks: list[Chunk],
    documents_repo: DocumentsRepository,
    chunks_repo: ChunksRepository,
) -> None:
    """chunking 完成後的共用尾段：embedding → 寫入 chunk（含向量）→ completed → auto_classify。

    embedding API 失敗（見 spec §2.5）視同解析失敗，標記 processing_status=failed，
    不寫入任何 chunk，避免留下沒有向量、DenseRetriever 永遠檢索不到的殘影資料。

    auto_classify 排在 completed 之後才觸發（見 spec §4.2 Demo 劇本）：分類需要已解析的
    chunk 內容，且分類失敗本身不影響文件是否可用，故不影響本函式回傳的 processing_status。
    """
    documents_repo.update_status(document_id, "embedding")
    try:
        vectors = await embed_texts(
            [chunk.content for chunk in chunks], tenant_id=tenant_id, user_id=user_id
        )
    except EmbeddingError as exc:
        logger.error("chunk embedding 生成失敗: doc=%s err=%s", document_id, exc)
        sentry_sdk.capture_exception(exc)
        documents_repo.update_status(document_id, "failed")
        return

    for chunk, vector in zip(chunks, vectors, strict=True):
        chunk.embedding = vector

    chunks_repo.bulk_insert(document_id, tenant_id, chunks)
    documents_repo.update_status(document_id, "completed")

    await auto_classify(
        document_id=document_id,
        tenant_id=tenant_id,
        user_id=user_id,
        file_name=file_name,
        chunk_texts=[chunk.content for chunk in chunks[:2]],
        documents_repo=documents_repo,
    )


async def process_pdf_document(
    document_id: str, tenant_id: str, user_id: str, file_bytes: bytes, file_name: str
) -> None:
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
        await _embed_and_store_chunks(
            document_id, tenant_id, user_id, file_name, chunks, documents_repo, chunks_repo
        )
    except (PDFParsingError, FallbackParsingError) as exc:
        logger.error("文件解析失敗（含 fallback）: doc=%s err=%s", document_id, exc)
        sentry_sdk.capture_exception(exc)
        documents_repo.update_status(document_id, "failed")
    except Exception as exc:
        logger.exception("文件處理管線發生未預期錯誤: doc=%s", document_id)
        sentry_sdk.capture_exception(exc)
        documents_repo.update_status(document_id, "failed")


async def process_xlsx_document(
    document_id: str, tenant_id: str, user_id: str, file_bytes: bytes, file_name: str
) -> None:
    """BackgroundTasks 派發的 XLSX pipeline：parsing → chunking → completed/failed（見 roadmap Day 4）。"""
    documents_repo = DocumentsRepository()
    chunks_repo = ChunksRepository()

    try:
        try:
            sheets = extract_xlsx_sheets(file_bytes)
            documents_repo.update_xlsx_sheets(document_id, sheets_to_json(sheets))
            documents_repo.update_status(document_id, "chunking")
            chunks = chunk_xlsx_sheets(sheets, settings.chunk_size_tokens)
        except XLSXParsingError as exc:
            logger.warning("pandas 解析失敗，觸發 LlamaParse fallback: doc=%s err=%s", document_id, exc)
            fallback_text = await LlamaParseAdapter().parse(file_bytes, file_name)
            documents_repo.update_status(document_id, "chunking")
            chunks = chunk_plain_text(fallback_text, settings.chunk_size_tokens, settings.chunk_overlap_tokens)

        await _embed_and_store_chunks(
            document_id, tenant_id, user_id, file_name, chunks, documents_repo, chunks_repo
        )
    except (XLSXParsingError, FallbackParsingError) as exc:
        logger.error("文件解析失敗（含 fallback）: doc=%s err=%s", document_id, exc)
        sentry_sdk.capture_exception(exc)
        documents_repo.update_status(document_id, "failed")
    except Exception as exc:
        logger.exception("文件處理管線發生未預期錯誤: doc=%s", document_id)
        sentry_sdk.capture_exception(exc)
        documents_repo.update_status(document_id, "failed")
