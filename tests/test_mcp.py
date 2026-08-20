"""Unit tests for Model Context Protocol (MCP) implementation."""

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from zeus.core.registry import REGISTRY, register_tool
from zeus.mcp.client import MCPClient
from zeus.mcp.config import MCPConfig, MCPServerConfig
from zeus.mcp.manager import MCPManager, get_mcp_manager
from zeus.mcp.protocol import (
    JsonRpcRequest,
    JsonRpcResponse,
    MCPToolParam,
    build_call_tool_request,
    build_initialize_request,
    build_initialized_notification,
    build_list_tools_request,
)
from zeus.mcp.server import MCPServer


def test_protocol_json_rpc_serialization():
    req = build_initialize_request(request_id=10)
    d = req.to_dict()
    assert d["jsonrpc"] == "2.0"
    assert d["method"] == "initialize"
    assert d["id"] == 10
    assert d["params"]["clientInfo"]["name"] == "zeus-agent"

    notif = build_initialized_notification()
    nd = notif.to_dict()
    assert nd["method"] == "notifications/initialized"
    assert "id" not in nd

    resp = JsonRpcResponse(id=10, result={"status": "ok"})
    rd = resp.to_dict()
    assert rd["id"] == 10
    assert rd["result"] == {"status": "ok"}


def test_mcp_config_load_save(tmp_path):
    cfg_file = tmp_path / "mcp_servers.json"
    cfg = MCPConfig(config_path=cfg_file)
    assert len(cfg.servers) == 0

    cfg.add_server("test_fs", "npx", args=["-y", "mcp-fs"], env={"KEY": "VAL"})
    assert "test_fs" in cfg.servers
    srv = cfg.servers["test_fs"]
    assert srv.command == "npx"
    assert srv.args == ["-y", "mcp-fs"]
    assert srv.env == {"KEY": "VAL"}

    # Reload from file
    cfg2 = MCPConfig(config_path=cfg_file)
    assert "test_fs" in cfg2.servers
    assert cfg2.servers["test_fs"].command == "npx"

    # Remove server
    assert cfg2.remove_server("test_fs")
    assert "test_fs" not in cfg2.servers


def test_mcp_server_handles_requests():
    # Register dummy tool in REGISTRY
    def dummy_tool(x: int):
        return {"result": x * 2}

    try:
        register_tool("dummy_test_tool", "Dummy description", {"type": "object", "properties": {"x": {"type": "integer"}}}, dummy_tool)
    except Exception:
        pass

    server = MCPServer(name="zeus-test-server")

    # Test initialize
    init_res = server.handle_request({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    assert init_res["result"]["serverInfo"]["name"] == "zeus-test-server"

    # Test tools/list
    tools_res = server.handle_request({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    tool_names = [t["name"] for t in tools_res["result"]["tools"]]
    assert "dummy_test_tool" in tool_names

    # Test tools/call
    call_res = server.handle_request({
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {"name": "dummy_test_tool", "arguments": {"x": 21}},
    })
    assert call_res["result"]["isError"] is False
    assert "42" in call_res["result"]["content"][0]["text"]


def test_mcp_client_handshake_and_tool_call():
    srv_cfg = MCPServerConfig(name="mock_srv", command="python", args=["-m", "mock"])
    client = MCPClient(srv_cfg)

    # Mock send_request for initialize and tools/list
    def mock_send_request(method, params=None, timeout=10.0):
        if method == "initialize":
            return {"id": 1, "result": {"protocolVersion": "2024-11-05"}}
        elif method == "tools/list":
            return {
                "id": 2,
                "result": {
                    "tools": [
                        {
                            "name": "mock_echo",
                            "description": "Echoes text",
                            "inputSchema": {"type": "object", "properties": {"msg": {"type": "string"}}},
                        }
                    ]
                },
            }
        elif method == "tools/call":
            return {
                "id": 3,
                "result": {
                    "content": [{"type": "text", "text": f"echoed: {params['arguments'].get('msg')}"}],
                    "isError": False,
                },
            }
        return {}

    client.send_request = mock_send_request
    client.send_notification = lambda m, p=None: None
    client.is_connected = True

    assert client._handshake() is True
    tools = client.refresh_tools()
    assert len(tools) == 1
    assert tools[0].name == "mock_echo"

    # Check registered tool in Zeus REGISTRY
    zeus_tool = REGISTRY.get("mcp_mock_srv_mock_echo")
    assert zeus_tool is not None

    # Call tool
    res = client.call_tool("mock_echo", {"msg": "hello zeus"})
    assert res["is_error"] is False
    assert "echoed: hello zeus" in res["output"]


def test_mcp_manager_singleton(tmp_path):
    cfg_file = tmp_path / "mcp_servers.json"
    mgr = MCPManager(config_path=cfg_file)
    mgr2 = get_mcp_manager()
    assert mgr is mgr2


def test_gemini_mcp_tools_registration():
    from zeus.mcp.gemini import register_gemini_mcp_tools
    register_gemini_mcp_tools()
    assert REGISTRY.get("gemini_search_grounding") is not None
    assert REGISTRY.get("gemini_code_execution") is not None

