import json
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.report import run_report_tool_calling

_MODULE = "app.services.report"


class _FakeFunctionCall:
    def __init__(self, name: str, arguments: str):
        self.name = name
        self.arguments = arguments


class _FakeToolCall:
    def __init__(self, call_id: str, name: str, arguments: str):
        self.id = call_id
        self.type = "function"
        self.function = _FakeFunctionCall(name, arguments)

    def model_dump(self):
        return {
            "id": self.id,
            "type": self.type,
            "function": {"name": self.function.name, "arguments": self.function.arguments},
        }


class _FakeMessage:
    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls


class _FakeChoice:
    def __init__(self, message):
        self.message = message


class _FakeResponse:
    def __init__(self, message):
        self.choices = [_FakeChoice(message)]


def _client_with_responses(*responses):
    client = MagicMock()
    client.chat.completions.create = AsyncMock(side_effect=list(responses))
    return client


async def test_run_report_tool_calling_without_tool_call_returns_direct_content():
    client = _client_with_responses(_FakeResponse(_FakeMessage(content="不需要工具就能回答")))

    with (
        patch(f"{_MODULE}._get_client", return_value=client),
        patch(f"{_MODULE}.build_xlsx_schema_summary", return_value=[]),
    ):
        result = await run_report_tool_calling(query="你好", tenant_id="tenant_a", role="admin")

    assert result == {"content": "不需要工具就能回答", "tool_calls": []}
    assert client.chat.completions.create.await_count == 1


async def test_run_report_tool_calling_executes_compute_table_metric_then_returns_final_content():
    tool_call = _FakeToolCall(
        "call-1",
        "compute_table_metric",
        json.dumps({"document_id": "doc-1", "sheet_name": "業績", "column": "業績 (NT$)", "operation": "sum"}),
    )
    first_response = _FakeResponse(_FakeMessage(content=None, tool_calls=[tool_call]))
    second_response = _FakeResponse(_FakeMessage(content="總業績為 400000"))
    client = _client_with_responses(first_response, second_response)

    fake_compute = AsyncMock(return_value={"status": "success", "result": 400000.0})

    with (
        patch(f"{_MODULE}._get_client", return_value=client),
        patch(f"{_MODULE}.build_xlsx_schema_summary", return_value=[{"document_id": "doc-1"}]),
        patch(f"{_MODULE}.compute_table_metric", new=fake_compute),
    ):
        result = await run_report_tool_calling(query="業績加總多少", tenant_id="tenant_a", role="admin")

    assert result["content"] == "總業績為 400000"
    assert result["tool_calls"] == [
        {
            "tool": "compute_table_metric",
            "arguments": tool_call.function.arguments,
            "result": {"status": "success", "result": 400000.0},
        }
    ]
    fake_compute.assert_awaited_once_with(
        tenant_id="tenant_a", document_id="doc-1", sheet_name="業績", column="業績 (NT$)", operation="sum"
    )
    assert client.chat.completions.create.await_count == 2

    # 第二輪呼叫不能再帶 tools，杜絕模型觸發第三輪 tool call（bounded 1-2 輪）
    second_call_kwargs = client.chat.completions.create.await_args_list[1].kwargs
    assert "tools" not in second_call_kwargs

    # tool 執行結果要以 role="tool" 訊息塞回對話，且內容跟 dispatch 結果一致
    sent_messages = second_call_kwargs["messages"]
    tool_messages = [m for m in sent_messages if m["role"] == "tool"]
    assert len(tool_messages) == 1
    assert json.loads(tool_messages[0]["content"]) == {"status": "success", "result": 400000.0}
    assert tool_messages[0]["tool_call_id"] == "call-1"


async def test_run_report_tool_calling_executes_query_documents():
    tool_call = _FakeToolCall("call-2", "query_documents", json.dumps({"query": "財報重點", "top_k": 3}))
    first_response = _FakeResponse(_FakeMessage(content=None, tool_calls=[tool_call]))
    second_response = _FakeResponse(_FakeMessage(content="根據檢索結果..."))
    client = _client_with_responses(first_response, second_response)

    fake_query = AsyncMock(return_value=[{"label": "財報.pdf，第 1 頁", "content": "重點內容"}])

    with (
        patch(f"{_MODULE}._get_client", return_value=client),
        patch(f"{_MODULE}.build_xlsx_schema_summary", return_value=[]),
        patch(f"{_MODULE}.query_documents", new=fake_query),
    ):
        result = await run_report_tool_calling(query="財報重點是什麼", tenant_id="tenant_a", role="viewer")

    assert result["content"] == "根據檢索結果..."
    fake_query.assert_awaited_once_with(
        query="財報重點", tenant_id="tenant_a", role="viewer", top_k=3, departments=None
    )


async def test_run_report_tool_calling_forwards_departments_to_query_documents():
    """report.py 的 departments 轉發需與 chat.py 一致，見 report_tools.py:79 的 query_documents。"""
    tool_call = _FakeToolCall("call-5", "query_documents", json.dumps({"query": "財報重點", "top_k": 3}))
    first_response = _FakeResponse(_FakeMessage(content=None, tool_calls=[tool_call]))
    second_response = _FakeResponse(_FakeMessage(content="根據檢索結果..."))
    client = _client_with_responses(first_response, second_response)

    fake_query = AsyncMock(return_value=[{"label": "財報.pdf，第 1 頁", "content": "重點內容"}])

    with (
        patch(f"{_MODULE}._get_client", return_value=client),
        patch(f"{_MODULE}.build_xlsx_schema_summary", return_value=[]),
        patch(f"{_MODULE}.query_documents", new=fake_query),
    ):
        await run_report_tool_calling(
            query="財報重點是什麼", tenant_id="tenant_a", role="viewer", departments=["財務部"]
        )

    fake_query.assert_awaited_once_with(
        query="財報重點", tenant_id="tenant_a", role="viewer", top_k=3, departments=["財務部"]
    )


async def test_run_report_tool_calling_unknown_tool_name_returns_structured_error_without_crashing():
    tool_call = _FakeToolCall("call-3", "delete_everything", "{}")
    first_response = _FakeResponse(_FakeMessage(content=None, tool_calls=[tool_call]))
    second_response = _FakeResponse(_FakeMessage(content="這個工具不存在，無法執行"))
    client = _client_with_responses(first_response, second_response)

    with (
        patch(f"{_MODULE}._get_client", return_value=client),
        patch(f"{_MODULE}.build_xlsx_schema_summary", return_value=[]),
        patch(f"{_MODULE}.sentry_sdk") as mock_sentry,
    ):
        result = await run_report_tool_calling(query="測試", tenant_id="tenant_a", role="admin")

    assert result["tool_calls"][0]["result"]["error_type"] == "UnknownTool"
    assert result["content"] == "這個工具不存在，無法執行"
    mock_sentry.capture_message.assert_called_once()


async def test_run_report_tool_calling_compute_table_metric_error_is_reported_to_sentry():
    """tool call 失敗路徑（見 spec §2.5 Observability）：結構化錯誤仍要送 Sentry 一份。"""
    tool_call = _FakeToolCall(
        "call-4",
        "compute_table_metric",
        json.dumps({"document_id": "doc-1", "sheet_name": "業績", "column": "不存在", "operation": "sum"}),
    )
    first_response = _FakeResponse(_FakeMessage(content=None, tool_calls=[tool_call]))
    second_response = _FakeResponse(_FakeMessage(content="找不到欄位，無法計算"))
    client = _client_with_responses(first_response, second_response)

    error_result = {"status": "error", "error_type": "ColumnNotFoundError", "message": "找不到欄位"}
    fake_compute = AsyncMock(return_value=error_result)

    with (
        patch(f"{_MODULE}._get_client", return_value=client),
        patch(f"{_MODULE}.build_xlsx_schema_summary", return_value=[]),
        patch(f"{_MODULE}.compute_table_metric", new=fake_compute),
        patch(f"{_MODULE}.sentry_sdk") as mock_sentry,
    ):
        result = await run_report_tool_calling(query="測試", tenant_id="tenant_a", role="admin")

    assert result["tool_calls"][0]["result"] == error_result
    mock_sentry.capture_message.assert_called_once()
    assert "compute_table_metric 失敗" in mock_sentry.capture_message.call_args.args[0]
