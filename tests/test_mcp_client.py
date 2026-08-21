"""Unit tests for zeus/mcp/client.py."""

from unittest.mock import MagicMock, patch

from zeus.mcp.client import MCPClient
from zeus.mcp.config import MCPServerConfig


def test_mcp_client_start_disabled():
    config = MCPServerConfig(name="test", command="echo", disabled=True)
    client = MCPClient(config)
    assert client.start() is False


def test_mcp_client_start_stdio_success():
    config = MCPServerConfig(name="echo", command="cat")
    client = MCPClient(config)

    def fake_handshake():
        client.is_connected = True
        return True

    with patch.object(client, "_handshake", fake_handshake):
        with patch.object(client, "refresh_tools", return_value=[]):
            ok = client.start()

    assert ok is True
    assert client.is_connected is True


def test_mcp_client_send_request_sse():
    config = MCPServerConfig(name="sse", url="http://example.com/mcp")
    client = MCPClient(config)
    client.is_connected = True

    mock_response = MagicMock()
    mock_response.json.return_value = {"jsonrpc": "2.0", "id": 1, "result": {"tools": []}}
    mock_response.raise_for_status = MagicMock()

    with patch("requests.post", return_value=mock_response):
        resp = client.send_request("tools/list")

    assert "result" in resp


def test_mcp_client_call_tool_success():
    config = MCPServerConfig(name="test", command="cat")
    client = MCPClient(config)
    client.is_connected = True

    def fake_send_request(method, params, timeout):
        return {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "content": [{"type": "text", "text": "hello"}],
                "isError": False,
            },
        }

    with patch.object(client, "send_request", fake_send_request):
        result = client.call_tool("greet", {"name": "world"})

    assert result["output"] == "hello"
    assert result["is_error"] is False


def test_mcp_client_call_tool_error_response():
    config = MCPServerConfig(name="test", command="cat")
    client = MCPClient(config)
    client.is_connected = True

    def fake_send_request(method, params, timeout):
        return {"jsonrpc": "2.0", "id": 1, "error": {"message": "boom"}}

    with patch.object(client, "send_request", fake_send_request):
        result = client.call_tool("greet", {})

    assert "error" in result


def test_mcp_client_call_tool_not_connected():
    config = MCPServerConfig(name="test", command="cat")
    client = MCPClient(config)
    result = client.call_tool("greet", {})
    assert "error" in result
    assert "not connected" in result["error"]


def test_mcp_client_stop():
    config = MCPServerConfig(name="test", command="cat")
    client = MCPClient(config)
    mock_proc = MagicMock()
    client.proc = mock_proc
    client.stop()
    mock_proc.terminate.assert_called_once()
    assert client.proc is None
