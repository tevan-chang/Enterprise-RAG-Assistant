from fastapi import APIRouter, Header
from fastapi.responses import StreamingResponse

from app.schemas.chat import ChatRequest
from app.services.chat import stream_chat_response

router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/query")
async def query(
    payload: ChatRequest,
    x_tenant_id: str = Header(alias="X-Tenant-Id"),
    x_user_role: str = Header(alias="X-User-Role"),
):
    """Chat 模式，SSE 串流回應（見 spec §2.3 / roadmap Day 6）。SSE 僅限本端點使用。"""
    return StreamingResponse(
        stream_chat_response(
            query=payload.query,
            tenant_id=x_tenant_id,
            role=x_user_role,
            departments=payload.departments,
            top_k=payload.top_k,
        ),
        media_type="text/event-stream",
    )
