from fastapi import APIRouter, Depends

from app.config import settings
from app.dependencies.auth import UserContext, get_current_user
from app.repositories.token_usage_repository import TokenUsageRepository
from app.schemas.usage import UsageResponse

router = APIRouter(prefix="/api/usage", tags=["usage"])


@router.get("", response_model=UsageResponse)
async def get_usage(user: UserContext = Depends(get_current_user)):
    """本租戶累計 token 用量與估算 cost（見 spec §10 Demo 版計費：只做累加 + 前端即時試算，
    不做真實計費結算/月結週期/額度阻擋）。任何已登入角色皆可查詢，不限 Editor/Admin。
    """
    repo = TokenUsageRepository()
    totals = repo.sum_by_tenant(user.tenant_id)
    prompt_tokens = totals["prompt_tokens"]
    completion_tokens = totals["completion_tokens"]
    cost = (
        prompt_tokens / 1000 * settings.token_price_per_1k_prompt_usd
        + completion_tokens / 1000 * settings.token_price_per_1k_completion_usd
    )
    return UsageResponse(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
        estimated_cost_usd=round(cost, 6),
    )
