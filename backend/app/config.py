from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    supabase_url: str = ""
    supabase_service_role_key: str = ""
    supabase_jwt_secret: str = ""

    llama_cloud_api_key: str = ""
    openai_api_key: str = ""

    chunk_size_tokens: int = 500
    chunk_overlap_tokens: int = 100
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536
    chat_model: str = "gpt-4o"

    zombie_task_timeout_minutes: int = 10

    retrieval_top_k: int = 5

    allowed_origins: str = "http://localhost:3000"

    @property
    def allowed_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]


settings = Settings()
