import hashlib

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, UploadFile

from app.repositories.chunks_repository import ChunksRepository
from app.repositories.documents_repository import DocumentsRepository
from app.schemas.documents import (
    ChunkOut,
    DocumentStatusResponse,
    DocumentUploadResponse,
    ReorganizeRequest,
    ReorganizeResponse,
    UnlockRequest,
    UnlockResponse,
)
from app.services.document_pipeline import process_pdf_document, process_xlsx_document

router = APIRouter(prefix="/api/documents", tags=["documents"])

_XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_PIPELINE_BY_CONTENT_TYPE = {
    "application/pdf": process_pdf_document,
    _XLSX_CONTENT_TYPE: process_xlsx_document,
}

# role-based 業務規則留在 FastAPI Query 層（見 spec §3.1），tenant_id 硬邊界交給 RLS。
_EDITOR_ROLES = {"admin", "editor"}
_ADMIN_ROLES = {"admin"}


def _require_role(allowed_roles: set[str]):
    def _dependency(x_user_role: str = Header(alias="X-User-Role")) -> str:
        if x_user_role not in allowed_roles:
            raise HTTPException(status_code=403, detail="權限不足")
        return x_user_role

    return _dependency


@router.post("/upload", response_model=DocumentUploadResponse)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile,
    x_tenant_id: str = Header(alias="X-Tenant-Id"),
):
    pipeline = _PIPELINE_BY_CONTENT_TYPE.get(file.content_type)
    if pipeline is None:
        raise HTTPException(status_code=422, detail="僅支援 PDF 或 XLSX 上傳")

    file_bytes = await file.read()
    file_content_hash = hashlib.sha256(file_bytes).hexdigest()
    documents_repo = DocumentsRepository()
    doc = documents_repo.create(
        tenant_id=x_tenant_id, file_name=file.filename, file_content_hash=file_content_hash
    )

    background_tasks.add_task(
        pipeline,
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


@router.post("/reorganize", response_model=ReorganizeResponse, dependencies=[Depends(_require_role(_EDITOR_ROLES))])
async def reorganize_document(payload: ReorganizeRequest):
    """手動整理：狀態鎖升級為 manually_verified（見 spec §4.2 / roadmap Day 5）。

    限 Editor/Admin，Viewer 無權編輯標籤（見 spec §3.2）。
    """
    documents_repo = DocumentsRepository()
    doc = documents_repo.reorganize(payload.document_id, payload.manual_categories)
    if doc is None:
        raise HTTPException(status_code=404, detail="文件不存在")

    return ReorganizeResponse(
        document_id=doc["id"],
        classification_status=doc["classification_status"],
        final_categories=doc["final_categories"],
    )


@router.post("/unlock", response_model=UnlockResponse, dependencies=[Depends(_require_role(_ADMIN_ROLES))])
async def unlock_documents(payload: UnlockRequest):
    """批次解鎖：狀態鎖降級為 auto_labeled，限 Admin（見 spec §3.2 / roadmap Day 5）。"""
    documents_repo = DocumentsRepository()
    unlocked = documents_repo.unlock_bulk(payload.document_ids)
    return UnlockResponse(unlocked_document_ids=[doc["id"] for doc in unlocked])
