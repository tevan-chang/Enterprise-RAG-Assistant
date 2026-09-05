from functools import lru_cache

import jwt
from fastapi import Depends, Header, HTTPException
from jwt import PyJWKClient
from pydantic import BaseModel

from app.config import settings


class UserContext(BaseModel):
    user_id: str
    tenant_id: str
    role: str


@lru_cache
def _jwks_client() -> PyJWKClient:
    return PyJWKClient(f"{settings.supabase_url}/auth/v1/.well-known/jwks.json")


def get_current_user(authorization: str = Header()) -> UserContext:
    """驗證 Supabase JWT，取代舊的 X-Tenant-Id / X-User-Role header 信任機制。
    tenant_id/role 只認 app_metadata（管理員經 Supabase Studio / Admin API
    設定），不是使用者可自行竄改的 user_metadata。

    Supabase 專案（本地與雲端實測皆同）預設用非對稱簽章金鑰（ES256）簽發 JWT，
    透過 JWKS endpoint 驗證；仍保留 HS256 + SUPABASE_JWT_SECRET 作為 fallback，
    因應舊專案可能仍在用 Legacy JWT Secret 的情況。
    """
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="缺少或格式錯誤的 Authorization header")

    try:
        alg = jwt.get_unverified_header(token).get("alg", "")
        if alg == "HS256":
            payload = jwt.decode(
                token,
                settings.supabase_jwt_secret,
                algorithms=["HS256"],
                audience="authenticated",
            )
        else:
            signing_key = _jwks_client().get_signing_key_from_jwt(token)
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=[alg or "ES256"],
                audience="authenticated",
            )
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="JWT 驗證失敗") from exc

    app_metadata = payload.get("app_metadata") or {}
    tenant_id = app_metadata.get("tenant_id")
    role = app_metadata.get("role")
    user_id = payload.get("sub")
    if not user_id or not tenant_id or not role:
        raise HTTPException(status_code=401, detail="JWT 缺少 tenant_id/role claim")

    return UserContext(user_id=user_id, tenant_id=tenant_id, role=role)


def require_role(allowed_roles: set[str]):
    def _dependency(user: UserContext = Depends(get_current_user)) -> UserContext:
        if user.role not in allowed_roles:
            raise HTTPException(status_code=403, detail="權限不足")
        return user

    return _dependency
