"""Sandbox execution tool backed by the Go sandbox server."""

from typing import Any, Dict

from zeus.core.registry import register_tool
from zeus.tools.sandbox_client import run_sandboxed_command


def run_sandboxed(command: str, timeout: int = 30) -> Dict[str, Any]:
    """Execute a command inside the sandboxed runtime."""
    from zeus.security.rate_limit import get_execution_limiter
    from zeus.tools.sandbox_client import current_user_session

    limiter = get_execution_limiter()
    user_id, session_id = current_user_session()
    if not limiter.is_allowed("run_sandboxed", user_id=user_id, session_id=session_id):
        return {"error": "Rate limit exceeded for run_sandboxed. Try again later."}

    result = run_sandboxed_command(command, timeout=timeout)
    from zeus.security.audit import get_audit_logger
    get_audit_logger().log_execution(tool="run_sandboxed", command=command, result=result)
    return result


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
    tags=["sandbox", "execute"],
)
