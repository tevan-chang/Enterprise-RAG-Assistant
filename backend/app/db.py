from functools import lru_cache

from supabase import Client, create_client

from app.config import settings


@lru_cache
def get_supabase_client() -> Client:
    """服務端 Supabase client，使用 service role key（略過 RLS）。

    RLS 只負責 tenant_id 硬邊界（見 spec §3.1）；confidentiality/role
    等業務規則過濾由 FastAPI Query 層自行實作，因此後端一律用 service
    role key，不透過使用者 JWT 連線。
    """
    return create_client(settings.supabase_url, settings.supabase_service_role_key)
