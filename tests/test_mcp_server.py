"""Unit tests for zeus/mcp/server.py."""

import json
from unittest.mock import MagicMock, patch

from zeus.mcp.server import MCPServer


def test_initialize_request():
    server = MCPServer()
    resp = server.handle_request({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    assert resp is not None
    assert resp["id"] == 1
    assert resp["result"]["serverInfo"]["name"] == "zeus-mcp-server"
    assert "protocolVersion" in resp["result"]


def test_notifications_initialized_returns_none():
    server = MCPServer()
    resp = server.handle_request({"jsonrpc": "2.0", "id": 2, "method": "notifications/initialized"})
    assert resp is None


def test_tools_list_returns_registered_tools():
    server = MCPServer()
    resp = server.handle_request({"jsonrpc": "2.0", "id": 3, "method": "tools/list"})
    assert resp is not None
    assert resp["id"] == 3
    assert "tools" in resp["result"]
    assert len(resp["result"]["tools"]) >= 0


def test_tools_call_unknown_tool():
    server = MCPServer()
    resp = server.handle_request({
        "jsonrpc": "2.0",
        "id": 4,
        "method": "tools/call",
        "params": {"name": "nonexistent_tool", "arguments": {}},
    })
    assert resp is not None
    assert resp["result"]["isError"] is True
    assert "not found" in resp["result"]["content"][0]["text"]


def test_tools_call_known_tool():
    server = MCPServer()

    fake_tool = MagicMock()
    fake_tool.name = "echo"
    fake_tool.description = "echo tool"
    fake_tool.parameters = {"type": "object"}
    fake_tool.handler = lambda msg: {"echo": msg}

    with patch("zeus.mcp.server.REGISTRY.get", side_effect=lambda name: fake_tool if name == "echo" else None):
        resp = server.handle_request({
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {"name": "echo", "arguments": {"msg": "hello"}},
        })

    assert resp is not None
    assert resp["result"]["isError"] is False
    text = json.loads(resp["result"]["content"][0]["text"])
    assert text["echo"] == "hello"


def test_unknown_method_returns_error():
    server = MCPServer()
    resp = server.handle_request({"jsonrpc": "2.0", "id": 6, "method": "unknown/method"})
    assert resp is not None
    assert resp["id"] == 6
    assert "error" in resp


def test_unknown_notification_returns_none():
    server = MCPServer()
    resp = server.handle_request({"jsonrpc": "2.0", "method": "unknown/notification"})
    assert resp is None
