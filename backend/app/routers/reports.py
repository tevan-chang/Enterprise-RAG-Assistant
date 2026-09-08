from fastapi import APIRouter, Depends

from app.dependencies.auth import UserContext, get_current_user
from app.schemas.reports import ReportGenerateRequest, ReportGenerateResponse
from app.services.report import run_report_tool_calling

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.post("/generate", response_model=ReportGenerateResponse)
async def generate_report(
    payload: ReportGenerateRequest,
    user: UserContext = Depends(get_current_user),
):
    """Report Mode（見 spec §2.4 / roadmap Day 8-9）：呼叫 bounded tool-calling 服務，
    整合 query_documents + compute_table_metric 兩個 tool 產出報告文字。

    tenant_id/role 一律由已驗證的 JWT 帶出，不接受 request body 指定
    （見 CLAUDE.md 雙層權限隔離），Viewer 的 confidentiality 過濾在 service 層處理。
    """
    result = await run_report_tool_calling(
        query=payload.query,
        tenant_id=user.tenant_id,
        role=user.role,
        user_id=user.user_id,
        departments=payload.departments,
    )
    return ReportGenerateResponse(content=result["content"] or "", tool_calls=result["tool_calls"])
