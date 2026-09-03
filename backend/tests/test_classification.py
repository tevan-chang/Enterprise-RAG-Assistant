import hashlib
from unittest.mock import MagicMock, patch

import pytest

from app.services.classification import on_file_reupload

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


def test_on_file_reupload_raises_when_document_missing():
    repo = _repo_returning(None)

    with pytest.raises(ValueError):
        on_file_reupload("missing-doc", b"content", documents_repo=repo)
