"""Tool registry: register and resolve tools available to the agent."""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set


@dataclass
class Tool:
    name: str
    description: str
    parameters: Dict[str, Any]
    handler: Callable[..., Any]
    required_env: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)


class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            self._tools[tool.name] = tool  # overwrite if re-registering
        else:
            self._tools[tool.name] = tool

    def unregister(self, name: str) -> bool:
        if name in self._tools:
            del self._tools[name]
            return True
        return False


    def get(self, name: str) -> Optional[Tool]:
        return self._tools.get(name)

    def list_tools(self) -> List[Tool]:
        return list(self._tools.values())

    def list_tags(self) -> List[str]:
        tags: Set[str] = set()
        for tool in self._tools.values():
            tags.update(tool.tags)
        return sorted(tags)

    def is_available(self, name: str) -> bool:
        tool = self._tools.get(name)
        if not tool:
            return False
        import os

        return all(os.getenv(env) for env in tool.required_env)

    def schemas(self, tag_allowlist: Optional[set] = None) -> List[Dict[str, Any]]:
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
            and (tag_allowlist is None or any(tag in tag_allowlist for tag in tool.tags))
        ]


REGISTRY = ToolRegistry()


def register_tool(
    name: str,
    description: str,
    parameters: Dict[str, Any],
    handler: Callable[..., Any],
    required_env: Optional[List[str]] = None,
    tags: Optional[List[str]] = None,
) -> Tool:
    tool = Tool(
        name=name,
        description=description,
        parameters=parameters,
        handler=handler,
        required_env=required_env or [],
        tags=tags or [],
    )
    REGISTRY.register(tool)
    return tool
