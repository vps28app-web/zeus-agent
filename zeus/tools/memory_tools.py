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


def search_memory(query: str) -> Dict[str, Any]:
    results = _store.search(query)
    return {"query": query, "count": len(results), "results": results}


def list_memories() -> Dict[str, Any]:
    keys = _store.keys()
    summary = {k: len(_store.get(k)) for k in keys}
    return {"keys": keys, "counts": summary}


def forget_memory(key: str) -> Dict[str, Any]:
    _store.clear(key)
    return {"deleted": True, "key": key}


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
    tags=["memory", "write"],
)

register_tool(
    name="recall",
    description="Retrieve notes from persistent memory by key.",
    parameters={
        "type": "object",
        "properties": {"key": {"type": "string", "default": "general"}},
        "required": [],
    },
    handler=recall,
    tags=["memory", "read"],
)

register_tool(
    name="search_memory",
    description="Search persistent memory notes by keyword or text.",
    parameters={
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    },
    handler=search_memory,
    tags=["memory", "read"],
)

register_tool(
    name="list_memories",
    description="List all memory keys and note counts.",
    parameters={"type": "object", "properties": {}},
    handler=list_memories,
    tags=["memory", "read"],
)

register_tool(
    name="forget_memory",
    description="Delete all persistent notes associated with a specific key.",
    parameters={
        "type": "object",
        "properties": {"key": {"type": "string"}},
        "required": ["key"],
    },
    handler=forget_memory,
    tags=["memory", "delete"],
)
