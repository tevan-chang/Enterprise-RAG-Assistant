from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, UploadFile

from app.repositories.chunks_repository import ChunksRepository
from app.repositories.documents_repository import DocumentsRepository
from app.schemas.documents import ChunkOut, DocumentStatusResponse, DocumentUploadResponse
from app.services.document_pipeline import process_pdf_document

router = APIRouter(prefix="/api/documents", tags=["documents"])

_ALLOWED_CONTENT_TYPES = {"application/pdf"}


@router.post("/upload", response_model=DocumentUploadResponse)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile,
    x_tenant_id: str = Header(alias="X-Tenant-Id"),
):
    if file.content_type not in _ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=422, detail="僅支援 PDF 上傳（XLSX 解析見 Day 4）")

    file_bytes = await file.read()
    documents_repo = DocumentsRepository()
    doc = documents_repo.create(tenant_id=x_tenant_id, file_name=file.filename)

    background_tasks.add_task(
        process_pdf_document,
        document_id=doc["id"],
        tenant_id=x_tenant_id,
        file_bytes=file_bytes,
        file_name=file.filename,
    )

    return DocumentUploadResponse(document_id=doc["id"], processing_status=doc["processing_status"])


@router.get("/{document_id}/status", response_model=DocumentStatusResponse)
async def get_document_status(document_id: str):
    documents_repo = DocumentsRepository()
    doc = documents_repo.get(document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="文件不存在")

    return DocumentStatusResponse(
        document_id=doc["id"],
        processing_status=doc["processing_status"],
        file_name=doc["file_name"],
        updated_at=doc["updated_at"],
    )


@router.get("/{document_id}/chunks", response_model=list[ChunkOut])
async def get_document_chunks(document_id: str):
    chunks_repo = ChunksRepository()
    return chunks_repo.list_by_document(document_id)
