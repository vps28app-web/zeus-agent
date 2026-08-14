"""Terminal/shell execution tool."""

import subprocess
from typing import Any, Dict

from zeus.core.registry import register_tool


def run_terminal(command: str, timeout: int = 60) -> Dict[str, Any]:
    """Run a shell command and return stdout, stderr, and exit code."""
    result = subprocess.run(
        command,
        shell=True,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=None,
    )
    return {
        "command": command,
        "exit_code": result.returncode,
        "stdout": result.stdout[:8000],
        "stderr": result.stderr[:4000],
    }


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
)
