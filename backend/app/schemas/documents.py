from pydantic import BaseModel, Field, field_validator


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
    sheet_name: str | None = None
    cell_range: str | None = None


class ChunkMatch(BaseModel):
    chunk_id: str
    document_id: str
    file_name: str
    page_number: int | None = None
    sheet_name: str | None = None
    cell_range: str | None = None
    content: str
    similarity: float


class ReorganizeRequest(BaseModel):
    document_id: str
    manual_categories: list[str] = Field(min_length=1)

    @field_validator("manual_categories")
    @classmethod
    def strip_and_reject_blank(cls, value: list[str]) -> list[str]:
        cleaned = [category.strip() for category in value]
        if any(not category for category in cleaned):
            raise ValueError("manual_categories 不可包含空白字串")
        return cleaned


class ReorganizeResponse(BaseModel):
    document_id: str
    classification_status: str
    final_categories: list[str]


class UnlockRequest(BaseModel):
    document_ids: list[str] = Field(min_length=1)


class UnlockResponse(BaseModel):
    unlocked_document_ids: list[str]
