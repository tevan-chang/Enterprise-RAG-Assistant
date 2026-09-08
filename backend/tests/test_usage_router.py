from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import settings
from app.dependencies.auth import UserContext, get_current_user
from app.routers import usage

_MODULE = "app.routers.usage"

_test_app = FastAPI()
_test_app.include_router(usage.router)
client = TestClient(_test_app)


@pytest.fixture(autouse=True)
def _clear_dependency_overrides():
    yield
    _test_app.dependency_overrides.clear()


def _as_user(tenant_id: str = "tenant_a", role: str = "viewer", user_id: str = "user-1"):
    _test_app.dependency_overrides[get_current_user] = lambda: UserContext(
        user_id=user_id, tenant_id=tenant_id, role=role
    )


def test_get_usage_returns_totals_and_estimated_cost():
    repo = MagicMock()
    repo.sum_by_tenant.return_value = {"prompt_tokens": 1000, "completion_tokens": 1000}
    _as_user(tenant_id="tenant_a")

    with patch(f"{_MODULE}.TokenUsageRepository", return_value=repo):
        resp = client.get("/api/usage")

    assert resp.status_code == 200
    body = resp.json()
    assert body["prompt_tokens"] == 1000
    assert body["completion_tokens"] == 1000
    assert body["total_tokens"] == 2000
    expected_cost = round(
        1000 / 1000 * settings.token_price_per_1k_prompt_usd
        + 1000 / 1000 * settings.token_price_per_1k_completion_usd,
        6,
    )
    assert body["estimated_cost_usd"] == expected_cost
    repo.sum_by_tenant.assert_called_once_with("tenant_a")


def test_get_usage_scoped_by_tenant():
    repo = MagicMock()
    repo.sum_by_tenant.return_value = {"prompt_tokens": 0, "completion_tokens": 0}
    _as_user(tenant_id="tenant_b")

    with patch(f"{_MODULE}.TokenUsageRepository", return_value=repo):
        resp = client.get("/api/usage")

    assert resp.status_code == 200
    assert resp.json() == {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "estimated_cost_usd": 0.0,
    }
    repo.sum_by_tenant.assert_called_once_with("tenant_b")


def test_get_usage_without_authorization_header_returns_422():
    resp = client.get("/api/usage")

    assert resp.status_code == 422
