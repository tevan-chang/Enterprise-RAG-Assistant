import hashlib

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile

from app.adapters.retrievers import VIEWER_ALLOWED_CONFIDENTIALITY
from app.dependencies.auth import UserContext, get_current_user, require_role
from app.repositories.chunks_repository import ChunksRepository
from app.repositories.documents_repository import DocumentsRepository
from app.schemas.documents import (
    ChunkOut,
    CitationDetailResponse,
    DocumentListItem,
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


@router.post("/upload", response_model=DocumentUploadResponse)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile,
    user: UserContext = Depends(get_current_user),
):
    pipeline = _PIPELINE_BY_CONTENT_TYPE.get(file.content_type)
    if pipeline is None:
        raise HTTPException(status_code=422, detail="僅支援 PDF 或 XLSX 上傳")

    file_bytes = await file.read()
    file_content_hash = hashlib.sha256(file_bytes).hexdigest()
    documents_repo = DocumentsRepository()
    doc = documents_repo.create(
        tenant_id=user.tenant_id, file_name=file.filename, file_content_hash=file_content_hash
    )

    background_tasks.add_task(
        pipeline,
        document_id=doc["id"],
        tenant_id=user.tenant_id,
        file_bytes=file_bytes,
        file_name=file.filename,
    )

    return DocumentUploadResponse(document_id=doc["id"], processing_status=doc["processing_status"])


@router.get("", response_model=list[DocumentListItem])
async def list_documents(user: UserContext = Depends(get_current_user)):
    """文件列表頁用（見 roadmap Day 5 前端串接），依 tenant_id 隔離。"""
    documents_repo = DocumentsRepository()
    docs = documents_repo.list_by_tenant(user.tenant_id)
    return [
        DocumentListItem(
            document_id=doc["id"],
            file_name=doc["file_name"],
            processing_status=doc["processing_status"],
            classification_status=doc["classification_status"],
            final_categories=doc["final_categories"],
            confidentiality=doc["confidentiality"],
            updated_at=doc["updated_at"],
        )
        for doc in docs
    ]


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


@router.get("/{document_id}/citation", response_model=CitationDetailResponse)
async def get_citation(
    document_id: str,
    user: UserContext = Depends(get_current_user),
    page_number: int | None = None,
    sheet_name: str | None = None,
    cell_range: str | None = None,
):
    """Citation 跳轉 API（見 roadmap Day 7）：依 PDF page_number 或 XLSX sheet_name+cell_range
    取回對應原文片段，供前端點擊 Chat citation 標籤後在 Modal 顯示。

    `repositories/` 一律用 service_role key bypass RLS（見 CLAUDE.md 雙層權限隔離），
    tenant_id 與 viewer confidentiality 過濾因此必須在這層做，不能只靠 DB。
    """
    if page_number is None and not (sheet_name and cell_range):
        raise HTTPException(status_code=422, detail="需提供 page_number，或 sheet_name+cell_range")

    documents_repo = DocumentsRepository()
    doc = documents_repo.get(document_id)
    if doc is None or doc["tenant_id"] != user.tenant_id:
        raise HTTPException(status_code=404, detail="文件不存在")
    if user.role == "viewer" and doc["confidentiality"] not in VIEWER_ALLOWED_CONFIDENTIALITY:
        raise HTTPException(status_code=403, detail="權限不足")

    chunks_repo = ChunksRepository()
    chunks = chunks_repo.list_by_location(
        document_id, page_number=page_number, sheet_name=sheet_name, cell_range=cell_range
    )
    if not chunks:
        raise HTTPException(status_code=404, detail="查無對應內容")

    return CitationDetailResponse(
        document_id=document_id,
        file_name=doc["file_name"],
        page_number=page_number,
        sheet_name=sheet_name,
        cell_range=cell_range,
        content="\n\n".join(chunk["content"] for chunk in chunks),
    )


@router.post("/reorganize", response_model=ReorganizeResponse, dependencies=[Depends(require_role(_EDITOR_ROLES))])
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


@router.post("/unlock", response_model=UnlockResponse, dependencies=[Depends(require_role(_ADMIN_ROLES))])
async def unlock_documents(payload: UnlockRequest):
    """批次解鎖：狀態鎖降級為 auto_labeled，限 Admin（見 spec §3.2 / roadmap Day 5）。"""
    documents_repo = DocumentsRepository()
    unlocked = documents_repo.unlock_bulk(payload.document_ids)
    return UnlockResponse(unlocked_document_ids=[doc["id"] for doc in unlocked])
