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

    # Gmail API 通知（見 spec §2.1 / roadmap Day 9-10）：google.oauth2.credentials.Credentials
    # 走 refresh_token 流程，不需要互動式 OAuth consent（一次性 setup 已在 GCP Console 完成）。
    gmail_oauth_client_id: str = ""
    gmail_oauth_client_secret: str = ""
    gmail_oauth_refresh_token: str = ""

    # 供外部 GitHub Actions Cron 打 /api/v1/admin/sync-knowledge-base 用的 API Key（見 spec §5）。
    sync_api_key: str = ""

    # Demo 階段三種通知情境（DOCUMENT_PROCESSED/FLAG_FOR_REVIEW/RAG_SYNC_COMPLETED）一律固定
    # 寄到這個信箱，不做「依上傳者/租戶動態決定收件人」的正式版（見使用者指示，之後再改）。
    admin_notification_email: str = "tevan090726@gmail.com"

    @property
    def allowed_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]


settings = Settings()
