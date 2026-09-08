from typing import Literal

from pydantic import BaseModel, Field, field_validator


class DocumentUploadResponse(BaseModel):
    document_id: str
    processing_status: str


class DocumentStatusResponse(BaseModel):
    document_id: str
    processing_status: str
    file_name: str
    updated_at: str


class DocumentListItem(BaseModel):
    document_id: str
    file_name: str
    processing_status: str
    classification_status: str
    final_categories: list[str]
    departments: list[str]
    confidentiality: str
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


class CitationDetailResponse(BaseModel):
    """Citation 跳轉 API 回應（見 roadmap Day 7）：PDF 用 page_number，XLSX 用 sheet_name+cell_range 定位。"""

    document_id: str
    file_name: str
    page_number: int | None = None
    sheet_name: str | None = None
    cell_range: str | None = None
    content: str


class ReorganizeRequest(BaseModel):
    document_id: str
    manual_categories: list[str] = Field(min_length=1)
    departments: list[str] | None = None
    confidentiality: Literal["public", "internal", "restricted"] | None = None

    @field_validator("manual_categories")
    @classmethod
    def strip_and_reject_blank(cls, value: list[str]) -> list[str]:
        cleaned = [category.strip() for category in value]
        if any(not category for category in cleaned):
            raise ValueError("manual_categories 不可包含空白字串")
        return cleaned

    @field_validator("departments")
    @classmethod
    def strip_departments(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        cleaned = [department.strip() for department in value]
        if any(not department for department in cleaned):
            raise ValueError("departments 不可包含空白字串")
        return cleaned


class ReorganizeResponse(BaseModel):
    document_id: str
    classification_status: str
    final_categories: list[str]
    departments: list[str]


class UnlockRequest(BaseModel):
    document_ids: list[str] = Field(min_length=1)


class UnlockResponse(BaseModel):
    unlocked_document_ids: list[str]


class DocumentDeleteResponse(BaseModel):
    document_id: str
