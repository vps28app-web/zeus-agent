"""Tool registry: register and resolve tools available to the agent."""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class Tool:
    name: str
    description: str
    parameters: Dict[str, Any]
    handler: Callable[..., Any]
    required_env: List[str] = field(default_factory=list)


class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[Tool]:
        return self._tools.get(name)

    def list_tools(self) -> List[Tool]:
        return list(self._tools.values())

    def is_available(self, name: str) -> bool:
        tool = self._tools.get(name)
        if not tool:
            return False
        import os

        return all(os.getenv(env) for env in tool.required_env)

    def schemas(self) -> List[Dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            }
            for tool in self._tools.values()
            if self.is_available(tool.name)
        ]


REGISTRY = ToolRegistry()


def register_tool(
    name: str,
    description: str,
    parameters: Dict[str, Any],
    handler: Callable[..., Any],
    required_env: Optional[List[str]] = None,
) -> Tool:
    tool = Tool(
        name=name,
        description=description,
        parameters=parameters,
        handler=handler,
        required_env=required_env or [],
    )
    REGISTRY.register(tool)
    return tool
