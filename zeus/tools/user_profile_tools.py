"""Tools for the agent to explicitly learn about users."""

from typing import Any, Dict, Optional

from zeus.core.registry import register_tool
from zeus.memory.user_profile import UserProfileStore

_store = UserProfileStore()


def remember_user(
    fact: str,
    user_id: Optional[str] = None,
    category: str = "preferences",
) -> Dict[str, Any]:
    """
    Store an explicit fact about the user.

    category must be one of: name, preferences, habits.
    """
    if category not in ("name", "preferences", "habits"):
        return {"error": f"Invalid category: {category}"}

    if user_id is None:
        # Fallback to a generic profile if no user context is available.
        user_id = "unknown"

    if category == "name":
        _store._repo.upsert(user_id=user_id, name=fact)
    elif category == "preferences":
        _store._repo.upsert(user_id=user_id, preferences=[fact])
    else:
        _store._repo.upsert(user_id=user_id, habits=[fact])

    return {"stored": True, "category": category, "fact": fact}


def recall_user(user_id: Optional[str] = None) -> Dict[str, Any]:
    """Return the stored profile for a user."""
    if user_id is None:
        user_id = "unknown"
    profile = _store.get_profile(user_id)
    if not profile:
        return {"found": False, "user_id": user_id}
    return {"found": True, "profile": profile}


register_tool(
    name="remember_user",
    description="Store an explicit fact about the user (name, preference, or habit).",
    parameters={
        "type": "object",
        "properties": {
            "fact": {"type": "string", "description": "The fact to remember about the user."},
            "category": {
                "type": "string",
                "enum": ["name", "preferences", "habits"],
                "default": "preferences",
                "description": "Category of the fact.",
            },
            "user_id": {
                "type": "string",
                "description": "Optional user identifier. Usually inferred by the system.",
            },
        },
        "required": ["fact"],
    },
    handler=remember_user,
    tags=["memory", "user", "write"],
)

register_tool(
    name="recall_user",
    description="Recall the stored profile for a user.",
    parameters={
        "type": "object",
        "properties": {
            "user_id": {
                "type": "string",
                "description": "Optional user identifier. Usually inferred by the system.",
            },
        },
    },
    handler=recall_user,
    tags=["memory", "user", "read"],
)
