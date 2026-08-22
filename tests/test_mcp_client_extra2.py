"""Additional unit tests for zeus/mcp/client.py edge cases."""

from unittest.mock import MagicMock, patch

from zeus.mcp.client import MCPClient
from zeus.mcp.config import MCPServerConfig


def test_start_sse_transport():
    config = MCPServerConfig(name="sse", url="http://example.com/mcp")
    client = MCPClient(config)

    with patch.object(client, "refresh_tools", return_value=[]) as mock_refresh:
        ok = client.start()

    assert ok is True
    assert client.is_connected is True
    mock_refresh.assert_called_once()


def test_start_stdio_process_launch_failure():
    config = MCPServerConfig(name="test", command="missing_binary_123")
    client = MCPClient(config)

    with patch("subprocess.Popen", side_effect=FileNotFoundError("not found")):
        ok = client.start()

    assert ok is False


def test_send_request_stdio_writes_to_stdin():
    config = MCPServerConfig(name="test", command="cat")
    client = MCPClient(config)

    mock_proc = MagicMock()
    mock_proc.poll.return_value = None
    mock_proc.stdin = MagicMock()
    client.proc = mock_proc

    mock_event = MagicMock()
    mock_event.wait.return_value = False
    client._pending_requests[1] = (mock_event, {})

    try:
        client.send_request("tools/list", timeout=0.01)
    except TimeoutError:
        pass

    mock_proc.stdin.write.assert_called_once()
    mock_proc.stdin.flush.assert_called_once()


def test_register_in_zeus_duplicate_ignored():
    config = MCPServerConfig(name="srv", command="cat")
    client = MCPClient(config)

    mock_tool = MagicMock()
    mock_tool.name = "tool1"
    mock_tool.description = "d"
    mock_tool.input_schema = {"type": "object", "properties": {}}

    with patch("zeus.mcp.client.register_tool", side_effect=Exception("already registered")):
        result = client._register_in_zeus(mock_tool)

    assert result is None
