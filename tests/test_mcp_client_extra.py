"""Additional unit tests for zeus/mcp/client.py."""

import json
import threading
from unittest.mock import MagicMock, patch

from zeus.mcp.client import MCPClient
from zeus.mcp.config import MCPServerConfig


def test_read_loop_resolves_pending_request():
    config = MCPServerConfig(name="test", command="cat")
    client = MCPClient(config)

    client._pending_requests[1] = (threading.Event(), {})
    client.proc = MagicMock()
    client.proc.poll.return_value = None
    client.proc.stdout.readline.side_effect = [
        json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"ok": True}}),
        "",
    ]

    client._read_loop()

    assert client._pending_requests[1][1].get("data") == {"jsonrpc": "2.0", "id": 1, "result": {"ok": True}}


def test_read_loop_ignores_invalid_json():
    config = MCPServerConfig(name="test", command="cat")
    client = MCPClient(config)
    client.proc = MagicMock()
    client.proc.poll.return_value = None
    client.proc.stdout.readline.side_effect = ["not json", ""]

    client._read_loop()

    assert client._pending_requests == {}


def test_handshake_success():
    config = MCPServerConfig(name="test", command="cat")
    client = MCPClient(config)

    def fake_send_request(method, params, timeout):
        return {"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "2024-11-05"}}

    sent_notifications = []

    def fake_send_notification(method, params):
        sent_notifications.append((method, params))

    with patch.object(client, "send_request", fake_send_request):
        with patch.object(client, "send_notification", fake_send_notification):
            ok = client._handshake()

    assert ok is True
    assert any(n[0] == "notifications/initialized" for n in sent_notifications)


def test_handshake_error_response():
    config = MCPServerConfig(name="test", command="cat")
    client = MCPClient(config)

    def fake_send_request(method, params, timeout):
        return {"jsonrpc": "2.0", "id": 1, "error": {"message": "fail"}}

    with patch.object(client, "send_request", fake_send_request):
        ok = client._handshake()

    assert ok is False


def test_handshake_exception_reads_stderr():
    config = MCPServerConfig(name="test", command="cat")
    client = MCPClient(config)

    def fake_send_request(method, params, timeout):
        raise TimeoutError("boom")

    mock_proc = MagicMock()
    mock_proc.stderr.readline.side_effect = ["error line", ""]
    client.proc = mock_proc

    with patch.object(client, "send_request", fake_send_request):
        ok = client._handshake()

    assert ok is False


def test_send_notification_stdio():
    config = MCPServerConfig(name="test", command="cat")
    client = MCPClient(config)

    mock_proc = MagicMock()
    mock_proc.stdin = MagicMock()
    client.proc = mock_proc

    client.send_notification("notifications/initialized", {})

    mock_proc.stdin.write.assert_called_once()
    mock_proc.stdin.flush.assert_called_once()


def test_send_request_stdio_timeout():
    config = MCPServerConfig(name="test", command="cat")
    client = MCPClient(config)

    mock_proc = MagicMock()
    mock_proc.stdin = MagicMock()
    client.proc = mock_proc

    with patch.object(client, "_lock"):
        pass

    try:
        client.send_request("tools/list", timeout=0.01)
        assert False, "should have timed out"
    except TimeoutError as e:
        assert "timed out" in str(e)


def test_refresh_tools_registers_tools():
    config = MCPServerConfig(name="test", command="cat")
    client = MCPClient(config)
    client.is_connected = True

    def fake_send_request(method, params, timeout):
        return {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "tools": [{
                    "name": "echo",
                    "description": "echo tool",
                    "inputSchema": {"type": "object", "properties": {}},
                }]
            },
        }

    with patch.object(client, "send_request", fake_send_request):
        tools = client.refresh_tools()

    assert len(tools) == 1
    assert "echo" in client.tools
    assert len(client.registered_zeus_tools) == 1


def test_register_in_zeus_collision_prefix():
    config = MCPServerConfig(name="srv", command="cat")
    client = MCPClient(config)

    mock_tool = MagicMock()
    mock_tool.name = "other_thing"
    mock_tool.description = "d"
    mock_tool.input_schema = {"type": "object", "properties": {}}

    zeus_tool = client._register_in_zeus(mock_tool)
    assert zeus_tool is not None
    assert zeus_tool.name == "mcp_srv_other_thing"


def test_call_tool_exception():
    config = MCPServerConfig(name="test", command="cat")
    client = MCPClient(config)
    client.is_connected = True

    def fake_send_request(method, params, timeout):
        raise RuntimeError("network down")

    with patch.object(client, "send_request", fake_send_request):
        result = client.call_tool("echo", {})

    assert "error" in result
    assert "network down" in result["error"]
