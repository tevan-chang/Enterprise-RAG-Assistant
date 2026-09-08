from app.db import get_supabase_client


class TokenUsageRepository:
    def __init__(self):
        self._client = get_supabase_client()

    def record(
        self,
        tenant_id: str,
        user_id: str,
        feature: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> None:
        self._client.table("token_usage").insert(
            {
                "tenant_id": tenant_id,
                "user_id": user_id,
                "feature": feature,
                "model": model,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
            }
        ).execute()

    def sum_by_tenant(self, tenant_id: str) -> dict:
        """GET /api/usage 用：本租戶累計 token 數（不分 feature，見 spec §10 Demo 版計費）。"""
        resp = (
            self._client.table("token_usage")
            .select("prompt_tokens, completion_tokens")
            .eq("tenant_id", tenant_id)
            .execute()
        )
        rows = resp.data or []
        return {
            "prompt_tokens": sum(row["prompt_tokens"] for row in rows),
            "completion_tokens": sum(row["completion_tokens"] for row in rows),
        }
