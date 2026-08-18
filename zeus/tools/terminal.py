"""Terminal/shell execution tool."""

import subprocess
from typing import Any, Dict

from zeus.core.registry import register_tool
from zeus.security.permissions import PermissionManager, check_shell_safety


_permissions = PermissionManager()


def run_terminal(command: str, timeout: int = 60) -> Dict[str, Any]:
    """Run a shell command and return stdout, stderr, and exit code."""
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
    description="Execute a shell command and return the output.",
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
