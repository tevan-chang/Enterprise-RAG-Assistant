import time

import jwt
import pytest
from fastapi import HTTPException

from app.config import settings
from app.dependencies.auth import get_current_user

_TEST_SECRET = "test-secret-not-real-but-at-least-32-bytes-long"


@pytest.fixture(autouse=True)
def _use_test_jwt_secret(monkeypatch):
    monkeypatch.setattr(settings, "supabase_jwt_secret", _TEST_SECRET)


def _make_token(app_metadata: dict | None = None, exp_delta: int = 3600, **overrides) -> str:
    payload = {
        "sub": "user-1",
        "aud": "authenticated",
        "role": "authenticated",
        "app_metadata": app_metadata if app_metadata is not None else {"tenant_id": "tenant_a", "role": "admin"},
        "exp": int(time.time()) + exp_delta,
    }
    payload.update(overrides)
    return jwt.encode(payload, _TEST_SECRET, algorithm="HS256")


def test_valid_token_returns_user_context():
    token = _make_token()

    user = get_current_user(authorization=f"Bearer {token}")

    assert user.user_id == "user-1"
    assert user.tenant_id == "tenant_a"
    assert user.role == "admin"


def test_missing_bearer_scheme_returns_401():
    token = _make_token()

    with pytest.raises(HTTPException) as exc_info:
        get_current_user(authorization=token)

    assert exc_info.value.status_code == 401


def test_wrong_scheme_returns_401():
    token = _make_token()

    with pytest.raises(HTTPException) as exc_info:
        get_current_user(authorization=f"Basic {token}")

    assert exc_info.value.status_code == 401


def test_invalid_signature_returns_401():
    token = jwt.encode(
        {
            "sub": "user-1",
            "aud": "authenticated",
            "app_metadata": {"tenant_id": "tenant_a", "role": "admin"},
            "exp": int(time.time()) + 3600,
        },
        "wrong-secret-but-also-at-least-32-bytes-long",
        algorithm="HS256",
    )

    with pytest.raises(HTTPException) as exc_info:
        get_current_user(authorization=f"Bearer {token}")

    assert exc_info.value.status_code == 401


def test_expired_token_returns_401():
    token = _make_token(exp_delta=-3600)

    with pytest.raises(HTTPException) as exc_info:
        get_current_user(authorization=f"Bearer {token}")

    assert exc_info.value.status_code == 401


def test_missing_tenant_id_claim_returns_401():
    token = _make_token(app_metadata={"role": "admin"})

    with pytest.raises(HTTPException) as exc_info:
        get_current_user(authorization=f"Bearer {token}")

    assert exc_info.value.status_code == 401


def test_missing_role_claim_returns_401():
    token = _make_token(app_metadata={"tenant_id": "tenant_a"})

    with pytest.raises(HTTPException) as exc_info:
        get_current_user(authorization=f"Bearer {token}")

    assert exc_info.value.status_code == 401


def test_wrong_audience_returns_401():
    token = jwt.encode(
        {
            "sub": "user-1",
            "aud": "anon",
            "app_metadata": {"tenant_id": "tenant_a", "role": "admin"},
            "exp": int(time.time()) + 3600,
        },
        _TEST_SECRET,
        algorithm="HS256",
    )

    with pytest.raises(HTTPException) as exc_info:
        get_current_user(authorization=f"Bearer {token}")

    assert exc_info.value.status_code == 401
