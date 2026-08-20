"""Model Context Protocol (MCP) JSON-RPC 2.0 specification and types."""

from dataclasses import dataclass, field
import json
from typing import Any, Dict, List, Optional, Union


MCP_PROTOCOL_VERSION = "2024-11-05"


@dataclass
class JsonRpcRequest:
    method: str
    params: Optional[Dict[str, Any]] = None
    id: Optional[Union[int, str]] = None
    jsonrpc: str = "2.0"

    def to_dict(self) -> Dict[str, Any]:
        msg: Dict[str, Any] = {"jsonrpc": self.jsonrpc, "method": self.method}
        if self.params is not None:
            msg["params"] = self.params
        if self.id is not None:
            msg["id"] = self.id
        return msg

    def to_json(self) -> str:
        return json.dumps(self.to_dict())


@dataclass
class JsonRpcResponse:
    id: Optional[Union[int, str]]
    result: Optional[Any] = None
    error: Optional[Dict[str, Any]] = None
    jsonrpc: str = "2.0"

    def to_dict(self) -> Dict[str, Any]:
        msg: Dict[str, Any] = {"jsonrpc": self.jsonrpc, "id": self.id}
        if self.error is not None:
            msg["error"] = self.error
        else:
            msg["result"] = self.result
        return msg

    def to_json(self) -> str:
        return json.dumps(self.to_dict())


@dataclass
class MCPToolParam:
    name: str
    description: str
    input_schema: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MCPToolParam":

        return cls(
            name=data.get("name", ""),
            description=data.get("description", ""),
            input_schema=data.get("inputSchema") or data.get("input_schema") or {"type": "object", "properties": {}},
        )


def build_initialize_request(
    client_name: str = "zeus-agent",
    client_version: str = "0.1.0",
    request_id: Union[int, str] = 1,
) -> JsonRpcRequest:
    return JsonRpcRequest(
        method="initialize",
        id=request_id,
        params={
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "capabilities": {
                "roots": {"listChanged": True},
                "sampling": {},
            },
            "clientInfo": {
                "name": client_name,
                "version": client_version,
            },
        },
    )


def build_initialized_notification() -> JsonRpcRequest:
    return JsonRpcRequest(
        method="notifications/initialized",
        params={},
    )


def build_list_tools_request(request_id: Union[int, str] = 2) -> JsonRpcRequest:
    return JsonRpcRequest(
        method="tools/list",
        id=request_id,
        params={},
    )


def build_call_tool_request(
    tool_name: str,
    arguments: Dict[str, Any],
    request_id: Union[int, str] = 3,
) -> JsonRpcRequest:
    return JsonRpcRequest(
        method="tools/call",
        id=request_id,
        params={
            "name": tool_name,
            "arguments": arguments,
        },
    )
