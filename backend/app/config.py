from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    supabase_url: str = ""
    supabase_service_role_key: str = ""
    supabase_jwt_secret: str = ""

    llama_cloud_api_key: str = ""
    openai_api_key: str = ""
    sentry_dsn: str = ""

    chunk_size_tokens: int = 500
    chunk_overlap_tokens: int = 100
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536
    chat_model: str = "gpt-4o"

    zombie_task_timeout_minutes: int = 10

    retrieval_top_k: int = 5

    # Demo 版計費用單一 blended 費率換算 cost（見 spec §10：只做累加 + 前端即時試算，
    # 不做真實計費結算），不分 chat/report/embedding/classification 分開計價，避免過度設計。
    token_price_per_1k_prompt_usd: float = 0.005
    token_price_per_1k_completion_usd: float = 0.015

    allowed_origins: str = "http://localhost:3000"

    @property
    def allowed_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]


settings = Settings()
