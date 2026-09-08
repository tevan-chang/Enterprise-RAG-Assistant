from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from openai import APIConnectionError

from app.config import settings
from app.services.chat import stream_chat_response

_MODULE = "app.services.chat"


class _FakeDelta:
    def __init__(self, content):
        self.content = content


class _FakeChoice:
    def __init__(self, content):
        self.delta = _FakeDelta(content)


class _FakeUsage:
    def __init__(self, prompt_tokens: int, completion_tokens: int):
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens


class _FakeChunk:
    def __init__(self, content, usage: _FakeUsage | None = None, has_choices: bool = True):
        self.choices = [_FakeChoice(content)] if has_choices else []
        self.usage = usage


class _FakeStream:
    """模擬 AsyncOpenAI stream=True + stream_options={"include_usage": True} 回傳的
    AsyncStream[ChatCompletionChunk]：`usage` 有值時，在 [DONE] 前多附加一個
    choices 為空陣列、只帶 usage 的 chunk（見 OpenAI Python SDK 定義）。
    """

    def __init__(self, contents, raise_after: Exception | None = None, usage: _FakeUsage | None = None):
        self._contents = contents
        self._raise_after = raise_after
        self._usage = usage

    def __aiter__(self):
        return self._gen()

    async def _gen(self):
        for content in self._contents:
            yield _FakeChunk(content)
        if self._raise_after is not None:
            raise self._raise_after
        if self._usage is not None:
            yield _FakeChunk(None, usage=self._usage, has_choices=False)


async def _collect(generator):
    return [event async for event in generator]


def _connection_error() -> APIConnectionError:
    return APIConnectionError(request=httpx.Request("POST", "https://api.openai.com/v1/chat/completions"))


@pytest.fixture(autouse=True)
def _mock_record_usage():
    """避免串流結束後的用量記錄打真實 Supabase（見 app/services/token_usage.py）；
    多數測試的 _FakeStream 不帶 usage，record_usage 本來就不會被呼叫，這個 fixture
    只是防呆，個別測試要驗證呼叫內容時把它當參數注入即可。
    """
    with patch(f"{_MODULE}.record_usage") as mock:
        yield mock


async def test_stream_chat_response_yields_message_and_done_events():
    retriever = MagicMock()
    retriever.retrieve = AsyncMock(
        return_value=[
            {
                "document_id": "doc-1",
                "file_name": "財報.pdf",
                "page_number": 3,
                "sheet_name": None,
                "cell_range": None,
                "content": "財報內容",
            }
        ]
    )
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=_FakeStream(["你好", "，世界"]))

    with (
        patch(f"{_MODULE}.DenseRetriever", return_value=retriever),
        patch(f"{_MODULE}._get_client", return_value=client),
    ):
        events = await _collect(
            stream_chat_response(query="測試問題", tenant_id="tenant_a", role="admin", user_id="user-1")
        )

    assert events == [
        'event: citations\ndata: {"citations": [{"label": "財報.pdf，第 3 頁", '
        '"document_id": "doc-1", "file_name": "財報.pdf", "page_number": 3, '
        '"sheet_name": null, "cell_range": null}]}\n\n',
        'event: message\ndata: {"delta": "你好"}\n\n',
        'event: message\ndata: {"delta": "，世界"}\n\n',
        "event: done\ndata: {}\n\n",
    ]
    retriever.retrieve.assert_called_once_with(
        query="測試問題", tenant_id="tenant_a", top_k=5, departments=None, role="admin"
    )


async def test_stream_chat_response_records_token_usage_after_stream_ends(_mock_record_usage):
    retriever = MagicMock()
    retriever.retrieve = AsyncMock(return_value=[])
    client = MagicMock()
    client.chat.completions.create = AsyncMock(
        return_value=_FakeStream(["你好"], usage=_FakeUsage(prompt_tokens=30, completion_tokens=8))
    )

    with (
        patch(f"{_MODULE}.DenseRetriever", return_value=retriever),
        patch(f"{_MODULE}._get_client", return_value=client),
    ):
        events = await _collect(
            stream_chat_response(query="測試問題", tenant_id="tenant_a", role="admin", user_id="user-1")
        )

    assert events[-1] == "event: done\ndata: {}\n\n"
    _mock_record_usage.assert_called_once_with(
        tenant_id="tenant_a",
        user_id="user-1",
        feature="chat",
        model=settings.chat_model,
        prompt_tokens=30,
        completion_tokens=8,
    )


async def test_stream_chat_response_dedupes_citations_and_formats_xlsx_label():
    """同一 sheet+cell_range 若被切成多個 chunk 命中，citations 事件應去重（見 roadmap Day 7）。"""
    retriever = MagicMock()
    retriever.retrieve = AsyncMock(
        return_value=[
            {
                "document_id": "doc-2",
                "file_name": "2026Q2.xlsx",
                "page_number": None,
                "sheet_name": "營收明細",
                "cell_range": "B2:D15",
                "content": "第一段",
            },
            {
                "document_id": "doc-2",
                "file_name": "2026Q2.xlsx",
                "page_number": None,
                "sheet_name": "營收明細",
                "cell_range": "B2:D15",
                "content": "第二段",
            },
        ]
    )
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=_FakeStream(["回答"]))

    with (
        patch(f"{_MODULE}.DenseRetriever", return_value=retriever),
        patch(f"{_MODULE}._get_client", return_value=client),
    ):
        events = await _collect(
            stream_chat_response(query="測試問題", tenant_id="tenant_a", role="admin", user_id="user-1")
        )

    assert events[0] == (
        'event: citations\ndata: {"citations": [{"label": "2026Q2.xlsx，工作表：營收明細 B2:D15", '
        '"document_id": "doc-2", "file_name": "2026Q2.xlsx", "page_number": null, '
        '"sheet_name": "營收明細", "cell_range": "B2:D15"}]}\n\n'
    )


async def test_stream_chat_response_without_hits_still_streams_and_says_unknown_capable():
    """未檢索到任何 chunk 時仍要能正常串流（prompt 已約束模型須答不知道，見 roadmap Day 6）。"""
    retriever = MagicMock()
    retriever.retrieve = AsyncMock(return_value=[])
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=_FakeStream(["目前查無相關資料，無法回答"]))

    with (
        patch(f"{_MODULE}.DenseRetriever", return_value=retriever),
        patch(f"{_MODULE}._get_client", return_value=client),
    ):
        events = await _collect(
            stream_chat_response(query="沒有相關資料的問題", tenant_id="tenant_a", role="viewer", user_id="user-1")
        )

    assert events[0] == 'event: message\ndata: {"delta": "目前查無相關資料，無法回答"}\n\n'
    assert events[-1] == "event: done\ndata: {}\n\n"


async def test_stream_chat_response_retrieval_failure_yields_error_event_only():
    retriever = MagicMock()
    retriever.retrieve = AsyncMock(side_effect=RuntimeError("db down"))

    with patch(f"{_MODULE}.DenseRetriever", return_value=retriever):
        events = await _collect(
            stream_chat_response(query="測試問題", tenant_id="tenant_a", role="admin", user_id="user-1")
        )

    assert len(events) == 1
    assert events[0].startswith("event: error\n")
    assert "db down" in events[0]


async def test_stream_chat_response_mid_stream_disconnect_yields_error_after_partial_message():
    retriever = MagicMock()
    retriever.retrieve = AsyncMock(return_value=[])
    client = MagicMock()
    client.chat.completions.create = AsyncMock(
        return_value=_FakeStream(["部分回應"], raise_after=_connection_error())
    )

    with (
        patch(f"{_MODULE}.DenseRetriever", return_value=retriever),
        patch(f"{_MODULE}._get_client", return_value=client),
    ):
        events = await _collect(
            stream_chat_response(query="測試問題", tenant_id="tenant_a", role="admin", user_id="user-1")
        )

    assert events[0] == 'event: message\ndata: {"delta": "部分回應"}\n\n'
    assert events[-1].startswith("event: error\n")
    assert "done" not in events[-1]
