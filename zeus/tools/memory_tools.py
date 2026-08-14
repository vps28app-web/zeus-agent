"""Memory tools for the agent to store and retrieve notes."""

from typing import Any, Dict, List

from zeus.core.registry import register_tool
from zeus.memory.store import MemoryStore


_store = MemoryStore()


def remember(note: str, key: str = "general") -> Dict[str, Any]:
    _store.append(key, note)
    return {"stored": True, "key": key}


def recall(key: str = "general") -> Dict[str, Any]:
    return {"key": key, "notes": _store.get(key)}


register_tool(
    name="remember",
    description="Store a note in persistent memory.",
    parameters={
        "type": "object",
        "properties": {
            "note": {"type": "string"},
            "key": {"type": "string", "default": "general"},
        },
        "required": ["note"],
    },
    handler=remember,
)

register_tool(
    name="recall",
    description="Retrieve notes from persistent memory.",
    parameters={
        "type": "object",
        "properties": {"key": {"type": "string", "default": "general"}},
        "required": [],
    },
    handler=recall,
)
