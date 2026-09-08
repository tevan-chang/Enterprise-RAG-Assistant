from unittest.mock import MagicMock, patch

from app.repositories.token_usage_repository import TokenUsageRepository

_MODULE = "app.repositories.token_usage_repository"


def _repo_with_mock_client() -> tuple[TokenUsageRepository, MagicMock]:
    with patch(f"{_MODULE}.get_supabase_client") as mock_get_client:
        client = MagicMock()
        mock_get_client.return_value = client
        repo = TokenUsageRepository()
    return repo, client


def test_record_inserts_row_with_all_fields():
    repo, client = _repo_with_mock_client()

    repo.record(
        tenant_id="tenant_a",
        user_id="user-1",
        feature="chat",
        model="gpt-4o",
        prompt_tokens=100,
        completion_tokens=50,
    )

    inserted_row = client.table.return_value.insert.call_args.args[0]
    assert inserted_row == {
        "tenant_id": "tenant_a",
        "user_id": "user-1",
        "feature": "chat",
        "model": "gpt-4o",
        "prompt_tokens": 100,
        "completion_tokens": 50,
    }
    client.table.return_value.insert.return_value.execute.assert_called_once()


def test_sum_by_tenant_aggregates_across_rows():
    repo, client = _repo_with_mock_client()
    client.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[
            {"prompt_tokens": 100, "completion_tokens": 50},
            {"prompt_tokens": 200, "completion_tokens": 0},
        ]
    )

    totals = repo.sum_by_tenant("tenant_a")

    assert totals == {"prompt_tokens": 300, "completion_tokens": 50}
    client.table.return_value.select.return_value.eq.assert_called_once_with("tenant_id", "tenant_a")


def test_sum_by_tenant_returns_zero_totals_when_no_rows():
    repo, client = _repo_with_mock_client()
    client.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

    totals = repo.sum_by_tenant("tenant_a")

    assert totals == {"prompt_tokens": 0, "completion_tokens": 0}
