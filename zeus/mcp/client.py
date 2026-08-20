"""MCP Client implementation for stdio and SSE transport."""

import json
import os
import subprocess
import threading
from typing import Any, Dict, List, Optional, Tuple

from zeus.core.registry import Tool, register_tool
from zeus.mcp.config import MCPServerConfig
from zeus.mcp.protocol import (
    MCPToolParam,
    build_call_tool_request,
    build_initialize_request,
    build_initialized_notification,
    build_list_tools_request,
)


class MCPClient:
    """Connects to a single MCP server (via stdio or SSE) and registers its tools."""

    def __init__(self, config: MCPServerConfig):
        self.config = config
        self.name = config.name
        self.proc: Optional[subprocess.Popen] = None
        self._next_id = 1
        self._lock = threading.Lock()
        self._pending_requests: Dict[int, Tuple[threading.Event, Dict[str, Any]]] = {}
        self._reader_thread: Optional[threading.Thread] = None
        self.tools: Dict[str, MCPToolParam] = {}
        self.registered_zeus_tools: List[Tool] = []
        self.is_connected = False

    def start(self) -> bool:
        """Start the transport process and run the MCP handshake."""
        if self.config.disabled:
            return False

        if self.config.command:
            return self._start_stdio()
        elif self.config.url:
            return self._start_sse()
        return False

    def _start_stdio(self) -> bool:
        env = os.environ.copy()
        env.update(self.config.env)

        cmd = [self.config.command] + self.config.args
        try:
            self.proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                env=env,
            )

            self._reader_thread = threading.Thread(target=self._read_loop, daemon=True)
            self._reader_thread.start()

            # Conduct JSON-RPC handshake
            if not self._handshake():
                self.stop()
                return False

            self.is_connected = True
            self.refresh_tools()
            return True
        except Exception as e:
            print(f"[MCPClient:{self.name}] Error starting stdio server '{cmd}': {e}")
            self.stop()
            return False

    def _start_sse(self) -> bool:
        """Connect to SSE remote MCP server."""
        # For SSE transport, mark connected and fetch tools via HTTP POST endpoint
        self.is_connected = True
        self.refresh_tools()
        return True

    def _read_loop(self) -> None:
        """Read lines from stdout and resolve pending RPC promises."""
        while self.proc and self.proc.poll() is None and self.proc.stdout:
            try:
                line = self.proc.stdout.readline()
                if not line:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue

                req_id = data.get("id")
                if req_id is not None:
                    with self._lock:
                        if req_id in self._pending_requests:
                            event, res_holder = self._pending_requests[req_id]
                            res_holder["data"] = data
                            event.set()
            except Exception:
                break

    def send_request(self, method: str, params: Optional[Dict[str, Any]] = None, timeout: float = 10.0) -> Dict[str, Any]:
        """Send a JSON-RPC request and wait for the response."""
        with self._lock:
            req_id = self._next_id
            self._next_id += 1
            event = threading.Event()
            res_holder: Dict[str, Any] = {}
            self._pending_requests[req_id] = (event, res_holder)

        req_data = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
        }
        if params is not None:
            req_data["params"] = params

        if self.proc and self.proc.stdin:
            try:
                msg = json.dumps(req_data) + "\n"
                self.proc.stdin.write(msg)
                self.proc.stdin.flush()
            except Exception as e:
                with self._lock:
                    self._pending_requests.pop(req_id, None)
                raise RuntimeError(f"Failed to send stdio message to MCP server {self.name}: {e}")

        elif self.config.url:
            import requests

            try:
                res = requests.post(self.config.url, json=req_data, timeout=timeout)
                res.raise_for_status()
                return res.json()
            except Exception as e:
                with self._lock:
                    self._pending_requests.pop(req_id, None)
                raise RuntimeError(f"Failed to send SSE request to {self.config.url}: {e}")

        if not event.wait(timeout=timeout):
            with self._lock:
                self._pending_requests.pop(req_id, None)
            raise TimeoutError(f"MCP server {self.name} timed out for method '{method}'")

        with self._lock:
            self._pending_requests.pop(req_id, None)

        return res_holder.get("data", {})

    def send_notification(self, method: str, params: Optional[Dict[str, Any]] = None) -> None:
        req_data = {
            "jsonrpc": "2.0",
            "method": method,
        }
        if params is not None:
            req_data["params"] = params

        if self.proc and self.proc.stdin:
            try:
                msg = json.dumps(req_data) + "\n"
                self.proc.stdin.write(msg)
                self.proc.stdin.flush()
            except Exception:
                pass

    def _handshake(self) -> bool:
        """Perform initialize -> notifications/initialized handshake."""
        try:
            req = build_initialize_request(request_id=self._next_id)
            resp = self.send_request(req.method, req.params, timeout=30.0)
            if "error" in resp:
                print(f"[MCPClient:{self.name}] Initialize error: {resp['error']}")
                return False

            init_notif = build_initialized_notification()
            self.send_notification(init_notif.method, init_notif.params)
            return True
        except Exception as e:
            stderr_msg = ""
            if self.proc and self.proc.stderr:
                try:
                    # Read any lines available on stderr
                    lines = []
                    while True:
                        line = self.proc.stderr.readline()
                        if not line:
                            break
                        lines.append(line.strip())
                    if lines:
                        stderr_msg = " | Stderr: " + " ".join(lines[:5])
                except Exception:
                    pass
            print(f"[MCPClient:{self.name}] Handshake failed: {e}{stderr_msg}")
            return False


    def refresh_tools(self) -> List[MCPToolParam]:
        """Fetch tools/list from server and register them in Zeus REGISTRY."""
        if not self.is_connected:
            return []

        try:
            req = build_list_tools_request(request_id=self._next_id)
            resp = self.send_request(req.method, req.params, timeout=10.0)
            result = resp.get("result", {})
            raw_tools = result.get("tools", [])

            self.tools.clear()
            self.registered_zeus_tools.clear()

            for t_dict in raw_tools:
                mcp_tool = MCPToolParam.from_dict(t_dict)
                self.tools[mcp_tool.name] = mcp_tool
                zeus_tool = self._register_in_zeus(mcp_tool)
                if zeus_tool:
                    self.registered_zeus_tools.append(zeus_tool)

            return list(self.tools.values())
        except Exception as e:
            print(f"[MCPClient:{self.name}] Failed to refresh tools: {e}")
            return []

    def _register_in_zeus(self, mcp_tool: MCPToolParam) -> Optional[Tool]:
        """Convert MCP Tool into a Zeus tool and register it."""
        # Sanitize tool name: prefix with mcp_<server_name>_ if collision occurs
        zeus_name = f"mcp_{self.name}_{mcp_tool.name}" if not mcp_tool.name.startswith("mcp_") else mcp_tool.name

        def make_handler(m_name=mcp_tool.name):
            def handler(**kwargs):
                return self.call_tool(m_name, kwargs)

            return handler

        schema_params = mcp_tool.input_schema
        if not isinstance(schema_params, dict) or "properties" not in schema_params:
            schema_params = {"type": "object", "properties": {}}

        try:
            return register_tool(
                name=zeus_name,
                description=f"[{self.name}] {mcp_tool.description}",
                parameters=schema_params,
                handler=make_handler(mcp_tool.name),
                tags=["mcp", self.name],
            )
        except Exception:
            # If tool already registered, ignore
            return None

    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Execute tools/call on the remote MCP server."""
        if not self.is_connected:
            return {"error": f"MCP server {self.name} is not connected"}

        try:
            req = build_call_tool_request(tool_name, arguments, request_id=self._next_id)
            resp = self.send_request(req.method, req.params, timeout=30.0)

            if "error" in resp:
                return {"error": resp["error"].get("message", "MCP Tool Error")}

            result = resp.get("result", {})
            content_list = result.get("content", [])

            text_outputs = []
            for item in content_list:
                if isinstance(item, dict) and item.get("type") == "text":
                    text_outputs.append(item.get("text", ""))

            combined_text = "\n".join(text_outputs) if text_outputs else json.dumps(result)
            return {
                "server": self.name,
                "tool": tool_name,
                "output": combined_text,
                "is_error": result.get("isError", False),
            }
        except Exception as e:
            return {"error": f"Failed to call MCP tool '{tool_name}' on server {self.name}: {e}"}

    def stop(self) -> None:
        """Shutdown transport process."""
        self.is_connected = False
        if self.proc:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=2.0)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass
            self.proc = None
