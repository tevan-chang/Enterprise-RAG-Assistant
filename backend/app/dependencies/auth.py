import jwt
from fastapi import Depends, Header, HTTPException
from pydantic import BaseModel

from app.config import settings


class UserContext(BaseModel):
    user_id: str
    tenant_id: str
    role: str


def get_current_user(authorization: str = Header()) -> UserContext:
    """驗證 Supabase JWT（Legacy JWT Secret / HS256），取代舊的
    X-Tenant-Id / X-User-Role header 信任機制。tenant_id/role 只認
    app_metadata（管理員經 Supabase Studio / Admin API 設定），不是
    使用者可自行竄改的 user_metadata。
    """
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="缺少或格式錯誤的 Authorization header")

    try:
        payload = jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
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
