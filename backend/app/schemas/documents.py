from pydantic import BaseModel, Field


class DocumentUploadResponse(BaseModel):
    document_id: str
    processing_status: str


class DocumentStatusResponse(BaseModel):
    document_id: str
    processing_status: str
    file_name: str
    updated_at: str


class ChunkOut(BaseModel):
    chunk_index: int
    page_number: int | None = None
    content: str
    token_count: int = Field(ge=0)
