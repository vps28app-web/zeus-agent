"""Additional unit tests for zeus/mcp/manager.py."""

from unittest.mock import MagicMock, patch

from zeus.mcp.manager import MCPManager


def test_add_server_gemini_without_key():
    manager = MCPManager()
    manager.clients = {}

    with patch.dict("os.environ", {"GEMINI_API_KEY": "", "GOOGLE_API_KEY": ""}, clear=False):
        with patch("zeus.mcp.gemini.register_gemini_mcp_tools") as mock_register:
            result = manager.add_server("gemini")

    assert result is True
    mock_register.assert_called_once()


def test_add_server_gemini_with_key():
    manager = MCPManager()
    manager.clients = {}

    with patch.dict("os.environ", {"GEMINI_API_KEY": "fake"}, clear=False):
        with patch("zeus.mcp.gemini.register_gemini_mcp_tools"):
            with patch.object(manager.config, "add_server") as mock_add:
                with patch.object(manager, "start_server", return_value=True):
                    manager.add_server("gemini")

    _, args, kwargs = mock_add.mock_calls[0]
    assert args[0] == "gemini"
    assert args[1] == "npx"
    assert "-y" in kwargs["args"]
    assert kwargs["env"]["GEMINI_API_KEY"] == "fake"


def test_add_server_memory():
    manager = MCPManager()
    manager.clients = {}

    with patch.object(manager.config, "add_server") as mock_add:
        with patch.object(manager, "start_server", return_value=True):
            manager.add_server("memory")

    _, args, kwargs = mock_add.mock_calls[0]
    assert args[0] == "memory"
    assert "@modelcontextprotocol/server-memory" in kwargs["args"]


def test_add_server_github():
    manager = MCPManager()
    manager.clients = {}

    with patch.object(manager.config, "add_server") as mock_add:
        with patch.object(manager, "start_server", return_value=True):
            manager.add_server("github")

    _, args, kwargs = mock_add.mock_calls[0]
    assert args[0] == "github"
    assert "@modelcontextprotocol/server-github" in kwargs["args"]


def test_stop_server_cleans_gemini_tools():
    manager = MCPManager()
    mock_client = MagicMock()
    manager.clients["gemini"] = mock_client

    with patch("zeus.core.registry.REGISTRY.unregister") as mock_unregister:
        with patch.object(manager.config, "servers", {}):
            manager.stop_server("gemini")

    gemini_calls = [c for c in mock_unregister.call_args_list if c[0][0] in ("gemini_search_grounding", "gemini_code_execution")]
    assert len(gemini_calls) == 2


def test_remove_server():
    manager = MCPManager()

    with patch.object(manager, "stop_server", return_value=True) as mock_stop:
        with patch.object(manager.config, "remove_server", return_value=True) as mock_remove:
            result = manager.remove_server("x")

    assert result is True
    mock_stop.assert_called_once_with("x")
    mock_remove.assert_called_once_with("x")
