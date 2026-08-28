"""Terminal/shell execution tool with background process management."""

import fcntl
import os
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from zeus.core.registry import register_tool
from zeus.security.permissions import (
    check_shell_safety,
    get_global_permission_manager,
)
from zeus.tools.sandbox_client import safe_environment

_permissions = get_global_permission_manager()
_background_processes: Dict[str, Dict[str, Any]] = {}


def run_terminal(command: str, timeout: int = 60, cwd: Optional[str] = None) -> Dict[str, Any]:
    """Run a shell command directly on the host and return stdout, stderr, and exit code.

    WARNING: Requires ZEUS_EXECUTION_PERMISSION=allow.
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

    working_dir = None
    if cwd:
        working_dir = str(Path(cwd).expanduser().resolve())
        if not Path(working_dir).exists():
            return {"error": f"Working directory does not exist: {cwd}"}

    result = subprocess.run(  # nosec B602
        command,
        shell=True,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=working_dir,
        env=safe_environment(),
    )
    output = {
        "command": command,
        "exit_code": result.returncode,
        "stdout": result.stdout[:8000],
        "stderr": result.stderr[:4000],
        "cwd": working_dir,
    }
    from zeus.security.audit import get_audit_logger
    get_audit_logger().log_execution(tool="run_terminal", command=command, result=output)
    return output


def run_background_command(command: str, cwd: Optional[str] = None) -> Dict[str, Any]:
    """Start a long-running shell command in the background and return its command_id."""
    from zeus.security.rate_limit import get_execution_limiter
    from zeus.tools.sandbox_client import current_user_session

    limiter = get_execution_limiter()
    user_id, session_id = current_user_session()
    if not limiter.is_allowed("run_terminal", user_id=user_id, session_id=session_id):
        return {"error": "Rate limit exceeded for run_background_command. Try again later."}

    if not _permissions.can_run_terminal():
        return {"error": _permissions.denied_message("run_terminal")}

    safety = check_shell_safety(command)
    if safety:
        return {"error": safety}

    working_dir = None
    if cwd:
        working_dir = str(Path(cwd).expanduser().resolve())
        if not Path(working_dir).exists():
            return {"error": f"Working directory does not exist: {cwd}"}

    cmd_id = f"cmd_{uuid.uuid4().hex[:8]}"
    proc = subprocess.Popen(
        command,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        cwd=working_dir,
        env=safe_environment(),
        start_new_session=True,
    )

    _background_processes[cmd_id] = {
        "command": command,
        "process": proc,
        "started_at": time.time(),
        "cwd": working_dir,
        "stdout_lines": [],
        "stderr_lines": [],
    }

    from zeus.security.audit import get_audit_logger
    get_audit_logger().log_execution(tool="run_background_command", command=command, result={"command_id": cmd_id, "pid": proc.pid})

    return {
        "status": "started",
        "command_id": cmd_id,
        "pid": proc.pid,
        "command": command,
        "cwd": working_dir,
        "message": f"Command started in background with ID {cmd_id}. Use command_status to check output.",
    }


def command_status(command_id: str, max_lines: int = 50) -> Dict[str, Any]:
    """Check status and read recent output of a background command."""
    if command_id not in _background_processes:
        return {"error": f"Background command ID not found: {command_id}"}

    entry = _background_processes[command_id]
    proc: subprocess.Popen = entry["process"]
    poll_res = proc.poll()

    # Read non-blocking output from streams
    for stream, key in [(proc.stdout, "stdout_lines"), (proc.stderr, "stderr_lines")]:
        if stream:
            try:
                fd = stream.fileno()
                fl = fcntl.fcntl(fd, fcntl.F_GETFL)
                fcntl.fcntl(fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)
                read_bytes = stream.read()
                if read_bytes:
                    entry[key].extend(read_bytes.splitlines())
            except Exception:
                pass

    is_running = (poll_res is None)
    return {
        "command_id": command_id,
        "command": entry["command"],
        "status": "running" if is_running else "finished",
        "exit_code": poll_res,
        "pid": proc.pid,
        "uptime_seconds": round(time.time() - entry["started_at"], 1),
        "stdout": entry["stdout_lines"][-max_lines:],
        "stderr": entry["stderr_lines"][-max_lines:],
    }


def terminate_command(command_id: str) -> Dict[str, Any]:
    """Terminate a running background command by command_id and its subprocess tree."""
    import signal

    if command_id not in _background_processes:
        return {"error": f"Background command ID not found: {command_id}"}

    entry = _background_processes[command_id]
    proc: subprocess.Popen = entry["process"]
    pid = proc.pid

    def kill_tree(sig: int) -> None:
        try:
            pgid = os.getpgid(pid)
            os.killpg(pgid, sig)
        except ProcessLookupError:
            pass
        except Exception:
            try:
                os.kill(pid, sig)
            except Exception:
                pass

    if proc.poll() is None:
        try:
            kill_tree(signal.SIGTERM)
            proc.wait(timeout=3)
        except Exception:
            try:
                kill_tree(signal.SIGKILL)
                proc.wait(timeout=2)
            except Exception:
                pass
        action_str = "terminated"
    else:
        action_str = "already_finished"

    return {
        "status": "success",
        "command_id": command_id,
        "action": action_str,
        "message": f"Process {command_id} (PID {pid}) status: {action_str}.",
    }


register_tool(
    name="run_terminal",
    description="Execute a shell command directly on the host (supports cwd).",
    parameters={
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "Shell command to execute."},
            "timeout": {"type": "integer", "description": "Timeout in seconds.", "default": 60},
            "cwd": {"type": "string", "description": "Working directory path."},
        },
        "required": ["command"],
    },
    handler=run_terminal,
    tags=["terminal", "execute"],
)

register_tool(
    name="run_background_command",
    description="Execute a shell command asynchronously in background (e.g. dev servers, long processes).",
    parameters={
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "Shell command to execute in background."},
            "cwd": {"type": "string", "description": "Working directory path."},
        },
        "required": ["command"],
    },
    handler=run_background_command,
    tags=["terminal", "execute"],
)

register_tool(
    name="command_status",
    description="Get running status and stdout/stderr output lines of a background command.",
    parameters={
        "type": "object",
        "properties": {
            "command_id": {"type": "string", "description": "ID returned by run_background_command."},
            "max_lines": {"type": "integer", "description": "Max recent output lines to return.", "default": 50},
        },
        "required": ["command_id"],
    },
    handler=command_status,
    tags=["terminal", "read"],
)

register_tool(
    name="terminate_command",
    description="Terminate a running background process by command_id.",
    parameters={
        "type": "object",
        "properties": {
            "command_id": {"type": "string", "description": "ID returned by run_background_command."},
        },
        "required": ["command_id"],
    },
    handler=terminate_command,
    tags=["terminal", "execute"],
)
