"""Central MCP Manager: handles active MCP clients and configuration."""

from typing import Dict, List, Optional

from zeus.mcp.client import MCPClient
from zeus.mcp.config import MCPConfig, MCPServerConfig


class MCPManager:
    """Singleton managing active MCP Clients and tool registration."""

    _instance: Optional["MCPManager"] = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def get_instance(cls) -> "MCPManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self, config_path=None):
        if hasattr(self, "_initialized") and self._initialized:
            return
        self.config = MCPConfig(config_path=config_path)
        self.clients: Dict[str, MCPClient] = {}
        self._initialized = True


    def start_all(self) -> Dict[str, bool]:
        """Start all configured MCP servers and register built-in tools."""
        from zeus.mcp.gemini import register_gemini_mcp_tools
        register_gemini_mcp_tools()

        results = {}
        for name, srv_config in self.config.servers.items():
            if not srv_config.disabled:
                results[name] = self.start_server(name)
        return results


    def start_server(self, name: str) -> bool:
        """Start a single MCP server client by name."""
        srv_config = self.config.servers.get(name)
        if not srv_config:
            return False

        if name in self.clients:
            self.clients[name].stop()

        client = MCPClient(srv_config)
        ok = client.start()
        if ok:
            self.clients[name] = client
        return ok

    def stop_server(self, name: str) -> bool:
        client = self.clients.pop(name, None)
        if client:
            client.stop()
        
        # Clean up any registered tools associated with this MCP server
        from zeus.core.registry import REGISTRY
        prefix = f"mcp_{name}_"
        tools_to_remove = [t_name for t_name in list(REGISTRY._tools.keys()) if t_name.startswith(prefix)]
        if name.lower() == "gemini":
            tools_to_remove.extend(["gemini_search_grounding", "gemini_code_execution"])

        for t_name in tools_to_remove:
            REGISTRY.unregister(t_name)

        return bool(client)


    def stop_all(self) -> None:
        for name in list(self.clients.keys()):
            self.stop_server(name)

    def reload(self) -> Dict[str, bool]:
        self.stop_all()
        self.config.load()
        return self.start_all()

    def add_server(
        self,
        name: str,
        command_or_url: Optional[str] = None,
        args: Optional[List[str]] = None,
        env: Optional[Dict[str, str]] = None,
    ) -> bool:
        cmd = command_or_url or name
        srv_args = args or []
        srv_env = env or {}

        # Handle presets
        lower_name = name.lower()
        lower_cmd = cmd.lower()
        if lower_name == "gemini" or lower_cmd == "gemini":
            from zeus.mcp.gemini import register_gemini_mcp_tools
            register_gemini_mcp_tools()

            import os
            api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
            if not api_key:
                print("\033[1;33m⚠️ GEMINI_API_KEY / GOOGLE_API_KEY não foi encontrada no ambiente.\033[0m")
                print("\033[90mAdicione GEMINI_API_KEY=sua_chave no arquivo .env para autenticar.\033[0m")
                print("\033[32m✅ Ferramentas Gemini nativas (grounding e code execution) foram registradas no Zeus.\033[0m")
                return True

            cmd = "npx"
            srv_args = ["-y", "@houtini/gemini-mcp"]
            srv_env["GEMINI_API_KEY"] = api_key


        elif lower_name == "filesystem" or lower_cmd == "filesystem":
            cmd = "npx"
            import os
            srv_args = ["-y", "@modelcontextprotocol/server-filesystem", os.getcwd()]
        elif lower_name == "memory" or lower_cmd == "memory":
            cmd = "npx"
            srv_args = ["-y", "@modelcontextprotocol/server-memory"]
        elif lower_name == "github" or lower_cmd == "github":
            cmd = "npx"
            srv_args = ["-y", "@modelcontextprotocol/server-github"]

        self.config.add_server(name, cmd, args=srv_args, env=srv_env)
        return self.start_server(name)



    def remove_server(self, name: str) -> bool:
        self.stop_server(name)
        return self.config.remove_server(name)

    def list_status(self) -> List[Dict]:
        status_list = []
        for name, srv in self.config.servers.items():
            client = self.clients.get(name)
            is_active = client.is_connected if client else False
            tool_count = len(client.tools) if client else 0
            status_list.append({
                "name": name,
                "type": "sse" if srv.url else "stdio",
                "command_or_url": srv.url or f"{srv.command} {' '.join(srv.args)}".strip(),
                "active": is_active,
                "disabled": srv.disabled,
                "tool_count": tool_count,
            })
        return status_list


def get_mcp_manager() -> MCPManager:
    return MCPManager()
