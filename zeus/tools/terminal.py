"""Terminal/shell execution tool."""

import subprocess
from typing import Any, Dict

from zeus.core.registry import register_tool
from zeus.security.permissions import PermissionManager, check_shell_safety
from zeus.tools.sandbox_client import safe_environment


_permissions = PermissionManager()


def run_terminal(command: str, timeout: int = 60) -> Dict[str, Any]:
    """Run a shell command directly on the host and return stdout, stderr, and exit code.

    WARNING: This bypasses the Go sandbox. It requires ZEUS_EXECUTION_PERMISSION=allow.
    Use run_sandboxed or execute_shell_script for isolated execution.
    """
    from zeus.security.rate_limit import get_execution_limiter
    from zeus.tools.sandbox_client import current_user_session

    limiter = get_execution_limiter()
    user_id, session_id = current_user_session()
    if not limiter.is_allowed("run_terminal", user_id=user_id, session_id=session_id):
        return {"error": "Rate limit exceeded for run_terminal. Try again later."}

    if not _permissions.can_run_terminal():
        from zeus.security.audit import get_audit_logger
        get_audit_logger().log_execution(
            tool="run_terminal", command=command,
            result={"error": _permissions.denied_message("run_terminal")},
            allowed=False,
        )
        return {"error": _permissions.denied_message("run_terminal")}

    safety = check_shell_safety(command)
    if safety:
        from zeus.security.audit import get_audit_logger
        get_audit_logger().log_execution(
            tool="run_terminal", command=command,
            result={"error": safety},
            allowed=False,
        )
        return {"error": safety}

    result = subprocess.run(
        command,
        shell=True,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=None,
        env=safe_environment(),
    )
    output = {
        "command": command,
        "exit_code": result.returncode,
        "stdout": result.stdout[:8000],
        "stderr": result.stderr[:4000],
    }
    from zeus.security.audit import get_audit_logger
    get_audit_logger().log_execution(tool="run_terminal", command=command, result=output)
    return output


register_tool(
    name="run_terminal",
    description="Execute a shell command directly on the host (requires ZEUS_EXECUTION_PERMISSION=allow; bypasses sandbox).",
    parameters={
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "Shell command to execute."},
            "timeout": {"type": "integer", "description": "Timeout in seconds.", "default": 60},
        },
        "required": ["command"],
    },
    handler=run_terminal,
    tags=["terminal", "execute"],
)
