from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    supabase_url: str = ""
    supabase_service_role_key: str = ""

    llama_cloud_api_key: str = ""

    chunk_size_tokens: int = 500
    chunk_overlap_tokens: int = 100
    embedding_model: str = "text-embedding-3-small"

    zombie_task_timeout_minutes: int = 10


settings = Settings()
