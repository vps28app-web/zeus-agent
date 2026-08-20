"""MCP Server configuration loader and manager."""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class MCPServerConfig:
    name: str
    command: Optional[str] = None
    args: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)
    url: Optional[str] = None  # For SSE transport
    disabled: bool = False

    @classmethod
    def from_dict(cls, name: str, data: Dict[str, Any]) -> "MCPServerConfig":

        return cls(
            name=name,
            command=data.get("command"),
            args=data.get("args") or [],
            env=data.get("env") or {},
            url=data.get("url"),
            disabled=data.get("disabled", False),
        )

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {}
        if self.url:
            d["url"] = self.url
        else:
            d["command"] = self.command
            d["args"] = self.args
            if self.env:
                d["env"] = self.env
        if self.disabled:
            d["disabled"] = True
        return d


class MCPConfig:
    """Manages MCP server configurations from JSON files."""

    def __init__(self, config_path: Optional[Path] = None):
        if config_path:
            self.config_path = config_path
        else:
            # Default to ~/.zeus/mcp_servers.json or ./mcp_servers.json
            zeus_home = Path(os.getenv("ZEUS_HOME", os.path.expanduser("~/.zeus")))
            local_cfg = Path.cwd() / "mcp_servers.json"
            if local_cfg.exists():
                self.config_path = local_cfg
            else:
                self.config_path = zeus_home / "mcp_servers.json"

        self.servers: Dict[str, MCPServerConfig] = {}
        self.load()

    def load(self) -> Dict[str, MCPServerConfig]:
        self.servers.clear()
        if not self.config_path.exists():
            return self.servers

        try:
            data = json.loads(self.config_path.read_text(encoding="utf-8"))
            mcp_servers = data.get("mcpServers") or data.get("mcp_servers") or data
            if isinstance(mcp_servers, dict):
                for name, srv_data in mcp_servers.items():
                    if isinstance(srv_data, dict):
                        self.servers[name] = MCPServerConfig.from_dict(name, srv_data)
        except Exception as e:
            print(f"[MCPConfig] Error loading {self.config_path}: {e}")

        return self.servers

    def save(self) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        data = {"mcpServers": {name: srv.to_dict() for name, srv in self.servers.items()}}
        self.config_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def add_server(
        self,
        name: str,
        command_or_url: str,
        args: Optional[List[str]] = None,
        env: Optional[Dict[str, str]] = None,
    ) -> MCPServerConfig:
        if command_or_url.startswith("http://") or command_or_url.startswith("https://"):
            srv = MCPServerConfig(name=name, url=command_or_url)
        else:
            srv = MCPServerConfig(name=name, command=command_or_url, args=args or [], env=env or {})
        self.servers[name] = srv
        self.save()
        return srv

    def remove_server(self, name: str) -> bool:
        if name in self.servers:
            del self.servers[name]
            self.save()
            return True
        return False
