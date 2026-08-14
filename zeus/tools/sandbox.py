"""Sandbox execution tool backed by the Go sandbox server."""

from typing import Any, Dict, Optional

from zeus.core.registry import register_tool
from zeus.tools.sandbox_client import run_sandboxed_command


def run_sandboxed(command: str, timeout: int = 30) -> Dict[str, Any]:
    """Execute a command inside the sandboxed runtime."""
    return run_sandboxed_command(command, timeout=timeout)


register_tool(
    name="run_sandboxed",
    description="Execute a shell command inside an isolated sandbox for safety.",
    parameters={
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "Shell command to execute in the sandbox."},
            "timeout": {"type": "integer", "description": "Timeout in seconds.", "default": 30},
        },
        "required": ["command"],
    },
    handler=run_sandboxed,
)
