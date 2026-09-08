from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.dependencies.auth import UserContext, get_current_user
from app.schemas.chat import ChatRequest
from app.services.chat import stream_chat_response

router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/query")
async def query(
    payload: ChatRequest,
    user: UserContext = Depends(get_current_user),
):
    """Chat 模式，SSE 串流回應（見 spec §2.3 / roadmap Day 6）。SSE 僅限本端點使用。"""
    return StreamingResponse(
        stream_chat_response(
            query=payload.query,
            tenant_id=user.tenant_id,
            role=user.role,
            user_id=user.user_id,
            departments=payload.departments,
            top_k=payload.top_k,
        ),
        media_type="text/event-stream",
    )
