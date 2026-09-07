from pydantic import BaseModel, Field, field_validator


class ReportGenerateRequest(BaseModel):
    query: str = Field(min_length=1)

    @field_validator("query")
    @classmethod
    def strip_and_reject_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("query 不可為空白字串")
        return cleaned


class ReportToolCallOut(BaseModel):
    """前端 tool-calling 過程可視化用（見 roadmap Day 9 前端串接）。"""

    tool: str
    arguments: str
    result: dict


class ReportGenerateResponse(BaseModel):
    content: str
    tool_calls: list[ReportToolCallOut]
