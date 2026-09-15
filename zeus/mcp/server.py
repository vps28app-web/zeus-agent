"""MCPServer implementation to expose Zeus tools to external MCP clients over stdio."""

import json
import os
import sys
from typing import Any, Dict, List, Optional

from zeus.core.registry import REGISTRY
from zeus.mcp.protocol import MCP_PROTOCOL_VERSION, JsonRpcResponse


class MCPServer:
    """Exposes Zeus tools to external MCP clients (Claude Desktop, Cursor, etc.) via stdio JSON-RPC."""

    def __init__(self, name: str = "zeus-mcp-server", version: str = "0.1.0"):
        self.name = name
        self.version = version
        # Optional shared secret for local MCP clients.
        self.auth_token = os.getenv("ZEUS_MCP_AUTH_TOKEN")

    def _is_authenticated(self, request_data: Dict[str, Any]) -> bool:
        if not self.auth_token:
            return True
        meta = request_data.get("meta") or {}
        token = meta.get("auth_token")
        return token == self.auth_token

    def _auth_error(self, req_id: Any) -> Dict[str, Any]:
        return JsonRpcResponse(
            id=req_id,
            error={"code": -32001, "message": "Unauthorized: invalid or missing auth_token"},
        ).to_dict()

    def handle_request(self, request_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        method = request_data.get("method")
        req_id = request_data.get("id")
        params = request_data.get("params", {}) or {}

        # initialize is intentionally public so clients can negotiate before auth.
        if method == "initialize":
            return JsonRpcResponse(
                id=req_id,
                result={
                    "protocolVersion": MCP_PROTOCOL_VERSION,
                    "capabilities": {
                        "tools": {"listChanged": False},
                    },
                    "serverInfo": {
                        "name": self.name,
                        "version": self.version,
                    },
                },
            ).to_dict()

        # All other methods require authentication when ZEUS_MCP_AUTH_TOKEN is set.
        if not self._is_authenticated(request_data):
            return self._auth_error(req_id)

        if method == "notifications/initialized":
            return None

        if method == "tools/list":
            tools_list: List[Dict[str, Any]] = []
            for tool in REGISTRY.list_tools():
                tools_list.append({
                    "name": tool.name,
                    "description": tool.description,
                    "inputSchema": tool.parameters,
                })
            return JsonRpcResponse(
                id=req_id,
                result={"tools": tools_list},
            ).to_dict()

        if method == "tools/call":
            tool_name = params.get("name")
            arguments = params.get("arguments", {}) or {}

            tool = REGISTRY.get(tool_name)
            if not tool:
                return JsonRpcResponse(
                    id=req_id,
                    result={
                        "content": [{"type": "text", "text": f"Error: Tool '{tool_name}' not found"}],
                        "isError": True,
                    },
                ).to_dict()

            try:
                res = tool.handler(**arguments)
                res_str = json.dumps(res) if isinstance(res, (dict, list)) else str(res)
                return JsonRpcResponse(
                    id=req_id,
                    result={
                        "content": [{"type": "text", "text": res_str}],
                        "isError": False,
                    },
                ).to_dict()
            except Exception as e:
                return JsonRpcResponse(
                    id=req_id,
                    result={
                        "content": [{"type": "text", "text": f"Error executing tool '{tool_name}': {e}"}],
                        "isError": True,
                    },
                ).to_dict()

        elif req_id is not None:
            return JsonRpcResponse(
                id=req_id,
                error={"code": -32601, "message": f"Method '{method}' not found"},
            ).to_dict()

        return None

    def run_stdio(self) -> None:
        """Read JSON-RPC lines from stdin and write JSON-RPC responses to stdout."""
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                req_data = json.loads(line)
                resp_data = self.handle_request(req_data)
                if resp_data:
                    sys.stdout.write(json.dumps(resp_data) + "\n")
                    sys.stdout.flush()
            except Exception as e:
                err_resp = JsonRpcResponse(
                    id=None,
                    error={"code": -32700, "message": f"Parse error: {e}"},
                ).to_dict()
                sys.stdout.write(json.dumps(err_resp) + "\n")
                sys.stdout.flush()


def main():
    server = MCPServer()
    server.run_stdio()


if __name__ == "__main__":
    main()
