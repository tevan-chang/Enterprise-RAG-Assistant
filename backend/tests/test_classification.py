import hashlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.classification import auto_classify, flag_for_review, on_file_reupload

_MODULE = "app.services.classification"


def _repo_returning(doc: dict | None) -> MagicMock:
    repo = MagicMock()
    repo.get.return_value = doc
    return repo


def test_on_file_reupload_flags_when_hash_changed_and_locked():
    old_hash = hashlib.sha256(b"old content").hexdigest()
    repo = _repo_returning({"file_content_hash": old_hash, "classification_status": "manually_verified"})

    with patch(f"{_MODULE}.flag_for_review") as mock_flag:
        triggered = on_file_reupload("doc-1", b"new content", documents_repo=repo)

    assert triggered is True
    mock_flag.assert_called_once_with("doc-1")


def test_on_file_reupload_does_not_auto_unlock():
    """DoD 關鍵斷言：flag_for_review 不會反過來改動 classification_status（不自動解鎖）。"""
    old_hash = hashlib.sha256(b"old content").hexdigest()
    repo = _repo_returning({"file_content_hash": old_hash, "classification_status": "manually_verified"})

    with patch(f"{_MODULE}.flag_for_review"):
        on_file_reupload("doc-1", b"new content", documents_repo=repo)

    repo.update_status.assert_not_called()
    assert not hasattr(repo, "reorganize") or not repo.reorganize.called


def test_on_file_reupload_skips_when_hash_unchanged():
    same_hash = hashlib.sha256(b"same content").hexdigest()
    repo = _repo_returning({"file_content_hash": same_hash, "classification_status": "manually_verified"})

    with patch(f"{_MODULE}.flag_for_review") as mock_flag:
        triggered = on_file_reupload("doc-1", b"same content", documents_repo=repo)

    assert triggered is False
    mock_flag.assert_not_called()


def test_on_file_reupload_skips_when_not_locked():
    repo = _repo_returning({"file_content_hash": "different-hash", "classification_status": "auto_labeled"})

    with patch(f"{_MODULE}.flag_for_review") as mock_flag:
        triggered = on_file_reupload("doc-1", b"new content", documents_repo=repo)

    assert triggered is False
    mock_flag.assert_not_called()


def test_flag_for_review_reports_to_sentry():
    with patch(f"{_MODULE}.sentry_sdk") as mock_sentry:
        flag_for_review("doc-1")

    mock_sentry.capture_message.assert_called_once()
    assert "doc-1" in mock_sentry.capture_message.call_args.args[0]


def test_on_file_reupload_raises_when_document_missing():
    repo = _repo_returning(None)

    with pytest.raises(ValueError):
        on_file_reupload("missing-doc", b"content", documents_repo=repo)


def _mock_openai_client(content: str) -> MagicMock:
    response = MagicMock()
    response.choices = [MagicMock(message=MagicMock(content=content))]
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=response)
    return client


async def test_auto_classify_writes_categories_on_success():
    repo = MagicMock()
    client = _mock_openai_client('["財務報表", "季度報告"]')

    with patch(f"{_MODULE}._get_client", return_value=client):
        await auto_classify(
            "doc-1", "tenant_a", "q3.pdf", ["第一段內容", "第二段內容"], documents_repo=repo
        )

    repo.apply_auto_classification.assert_called_once_with(
        "doc-1", ["財務報表", "季度報告"], "tenant_a"
    )


async def test_auto_classify_delegates_lock_enforcement_to_repository():
    """auto_classify 本身不判斷鎖定狀態，一律呼叫 apply_auto_classification；真正擋下覆蓋
    manually_verified 文件的是該 repository 方法的 WHERE 條件（見 test_documents_repository.py），
    這裡只驗證即使 repo 因鎖定而回傳 None（未更新任何列），auto_classify 也不會例外或重試。
    """
    repo = MagicMock()
    repo.apply_auto_classification.return_value = None
    client = _mock_openai_client('["財務報表"]')

    with patch(f"{_MODULE}._get_client", return_value=client):
        await auto_classify("doc-1", "tenant_a", "q3.pdf", ["內容"], documents_repo=repo)

    repo.apply_auto_classification.assert_called_once_with("doc-1", ["財務報表"], "tenant_a")


async def test_auto_classify_swallows_llm_error_and_reports_sentry():
    repo = MagicMock()
    client = MagicMock()
    client.chat.completions.create = AsyncMock(side_effect=RuntimeError("openai down"))

    with (
        patch(f"{_MODULE}._get_client", return_value=client),
        patch(f"{_MODULE}.sentry_sdk") as mock_sentry,
    ):
        await auto_classify("doc-1", "tenant_a", "q3.pdf", ["內容"], documents_repo=repo)

    mock_sentry.capture_exception.assert_called_once()
    repo.apply_auto_classification.assert_not_called()


async def test_auto_classify_swallows_invalid_json_and_reports_sentry():
    repo = MagicMock()
    client = _mock_openai_client("不是 JSON 的自由文字回覆")

    with (
        patch(f"{_MODULE}._get_client", return_value=client),
        patch(f"{_MODULE}.sentry_sdk") as mock_sentry,
    ):
        await auto_classify("doc-1", "tenant_a", "q3.pdf", ["內容"], documents_repo=repo)

    mock_sentry.capture_exception.assert_called_once()
    repo.apply_auto_classification.assert_not_called()
