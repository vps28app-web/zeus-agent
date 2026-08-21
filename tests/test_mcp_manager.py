"""Unit tests for zeus/mcp/manager.py."""

from unittest.mock import MagicMock, patch

from zeus.mcp.manager import MCPManager, get_mcp_manager


def test_mcp_manager_singleton():
    m1 = get_mcp_manager()
    m2 = get_mcp_manager()
    assert m1 is m2


def test_start_server_registers_client():
    manager = MCPManager()
    manager.clients = {}

    mock_config = MagicMock()
    mock_config.servers = {"test": MagicMock(disabled=False)}
    manager.config = mock_config

    mock_client = MagicMock()
    mock_client.start.return_value = True

    with patch("zeus.mcp.manager.MCPClient", return_value=mock_client):
        with patch("zeus.mcp.gemini.register_gemini_mcp_tools"):
            ok = manager.start_server("test")

    assert ok is True
    assert manager.clients["test"] is mock_client


def test_start_server_missing_config():
    manager = MCPManager()
    manager.config = MagicMock()
    manager.config.servers = {}
    assert manager.start_server("missing") is False


def test_stop_server_removes_tools():
    manager = MCPManager()
    mock_client = MagicMock()
    manager.clients["test"] = mock_client

    with patch("zeus.core.registry.REGISTRY.unregister"):
        with patch.object(manager.config, "servers", {}):
            result = manager.stop_server("test")

    assert result is True
    mock_client.stop.assert_called_once()
    assert "test" not in manager.clients


def test_stop_all_stops_every_client():
    manager = MCPManager()
    manager.clients = {"a": MagicMock(), "b": MagicMock()}

    with patch.object(manager, "stop_server") as mock_stop:
        manager.stop_all()

    assert mock_stop.call_count == 2


def test_reload_restarts_servers():
    manager = MCPManager()

    with patch.object(manager, "stop_all") as mock_stop:
        with patch.object(manager.config, "load") as mock_load:
            with patch.object(manager, "start_all", return_value={"x": True}) as mock_start:
                result = manager.reload()

    mock_stop.assert_called_once()
    mock_load.assert_called_once()
    mock_start.assert_called_once()
    assert result == {"x": True}


def test_add_server_preset_filesystem():
    manager = MCPManager()
    manager.clients = {}

    with patch.object(manager, "start_server", return_value=True):
        with patch.object(manager.config, "add_server") as mock_add:
            result = manager.add_server("filesystem")

    assert result is True
    mock_add.assert_called_once()
    _, args, kwargs = mock_add.mock_calls[0]
    assert args[0] == "filesystem"
    assert args[1] == "npx"
    assert "@modelcontextprotocol/server-filesystem" in kwargs["args"]


def test_list_status_reflects_clients():
    manager = MCPManager()
    mock_client = MagicMock()
    mock_client.is_connected = True
    mock_client.tools = {"t1": MagicMock()}
    manager.clients["test"] = mock_client

    mock_srv = MagicMock()
    mock_srv.disabled = False
    mock_srv.url = None
    mock_srv.command = "cat"
    mock_srv.args = []
    manager.config.servers = {"test": mock_srv}

    status = manager.list_status()
    assert len(status) == 1
    assert status[0]["active"] is True
    assert status[0]["tool_count"] == 1
