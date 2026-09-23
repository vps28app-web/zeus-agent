"""Terminal/shell execution tool with background process management."""

import fcntl
import os
import re
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from zeus.core.registry import register_tool
from zeus.security.permissions import get_global_permission_manager
from zeus.tools.sandbox_client import safe_environment

_background_processes: Dict[str, Dict[str, Any]] = {}

# Optional live-output callback, registered by the CLI so the user can watch
# command output in real time instead of waiting for the process to finish.
_stream_callback: Optional[Callable[[str, str], None]] = None


def set_stream_callback(callback: Optional[Callable[[str, str], None]]) -> None:
    """Register a callback(chunk, stream) invoked as command output arrives."""
    global _stream_callback
    _stream_callback = callback


def _permissions():
    """Return the current global PermissionManager (may change at runtime via /mode)."""
    return get_global_permission_manager()


_SUDO_RE = re.compile(r"(^|[;&|(\n]\s*)sudo(?![A-Za-z0-9_-])")


def _needs_sudo(command: str) -> bool:
    """Return True if the command invokes sudo as a distinct word."""
    return bool(_SUDO_RE.search(command))


def _read_stream(stream, stream_name: str, chunks: Dict[str, str], lock: threading.Lock) -> None:
    """Read a process stream line by line, feeding live output and buffering."""
    try:
        for raw in iter(stream.readline, ""):
            if not raw:
                break
            with lock:
                chunks[stream_name] += raw
            if _stream_callback:
                try:
                    _stream_callback(raw.rstrip("\n"), stream_name)
                except Exception:
                    pass
    except Exception:
        pass
    finally:
        try:
            stream.close()
        except Exception:
            pass


def _run_with_optional_sudo(command: str, timeout: int, cwd, pm) -> Dict[str, Any]:
    """Run a shell command, prompting for sudo password if the command needs it.

    The password is read via the secure callback (never echoed), passed to
    `sudo -S` on stdin, and dropped from memory immediately after use.
    Output is streamed live via the stream callback (when registered) so the
    user can tell the command is progressing, not stuck.
    """
    env = safe_environment()
    needs_sudo = _needs_sudo(command)

    run_command = command
    password: Optional[str] = None
    if needs_sudo:
        # Ask for the password securely (cached for the session).
        password = pm.ask_password(
            f"O comando requer sudo:\n  {command}",
            cache_key="sudo",
        )
        if password is None:
            return {
                "exit_code": 1,
                "stdout": "",
                "stderr": "Sudo password not provided / senha sudo não fornecida.",
            }
        # Replace first `sudo` with `sudo -S` so it reads the password from stdin.
        run_command = _SUDO_RE.sub(r"\1sudo -S", command, count=1)

    try:
        popen_kwargs: Dict[str, Any] = {
            "shell": True,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "text": True,
            "bufsize": 1,
            "cwd": cwd,
            "env": env,
        }
        if password is not None:
            popen_kwargs["stdin"] = subprocess.PIPE
        proc = subprocess.Popen(run_command, **popen_kwargs)  # nosec B602
    except Exception as e:
        return {"exit_code": 1, "stdout": "", "stderr": f"Failed to start command: {e}"}

    if password is not None and proc.stdin is not None:
        try:
            proc.stdin.write(password + "\n")
            proc.stdin.flush()
            proc.stdin.close()
        finally:
            password = None

    chunks: Dict[str, str] = {"stdout": "", "stderr": ""}
    lock = threading.Lock()
    threads = []
    for stream, name in ((proc.stdout, "stdout"), (proc.stderr, "stderr")):
        if stream is not None:
            t = threading.Thread(target=_read_stream, args=(stream, name, chunks, lock), daemon=True)
            t.start()
            threads.append(t)

    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
        for t in threads:
            t.join(timeout=1)
        return {
            "exit_code": 124,
            "stdout": chunks["stdout"][:8000],
            "stderr": (chunks["stderr"] + f"\n[timeout após {timeout}s / timed out after {timeout}s]")[:4000],
        }

    for t in threads:
        t.join(timeout=2)

    return {
        "exit_code": proc.returncode,
        "stdout": chunks["stdout"][:8000],
        "stderr": chunks["stderr"][:4000],
    }


def run_terminal(command: str, timeout: int = 60, cwd: Optional[str] = None) -> Dict[str, Any]:
    """Run a shell command directly on the host and return stdout, stderr, and exit code.

    WARNING: Requires ZEUS_EXECUTION_PERMISSION=allow.
    """
    from zeus.security.rate_limit import get_execution_limiter
    from zeus.tools.sandbox_client import current_user_session

    pm = _permissions()

    limiter = get_execution_limiter()
    user_id, session_id = current_user_session()
    if not limiter.is_allowed("run_terminal", user_id=user_id, session_id=session_id):
        return {"error": "Rate limit exceeded for run_terminal. Try again later."}

    if not pm.can_run_terminal():
        from zeus.security.audit import get_audit_logger
        get_audit_logger().log_execution(
            tool="run_terminal", command=command,
            result={"error": pm.denied_message("run_terminal")},
            allowed=False,
        )
        return {"error": pm.denied_message("run_terminal")}

    # In terminal mode every command requires explicit user confirmation
    # (the user authorizes any command). Auto/other modes execute immediately
    # once host execution is allowed.
    if pm.is_confirmation_required("run_terminal", {"command": command}):
        if not pm.confirm_tool("run_terminal", {"command": command}):
            from zeus.security.audit import get_audit_logger
            get_audit_logger().log_execution(
                tool="run_terminal", command=command,
                result={"error": "Execution denied by user."},
                allowed=False,
            )
            return {"error": "Execution denied by user / Execução negada pelo usuário."}

    working_dir = None
    if cwd:
        working_dir = str(Path(cwd).expanduser().resolve())
        if not Path(working_dir).exists():
            return {"error": f"Working directory does not exist: {cwd}"}

    result = _run_with_optional_sudo(command, timeout, working_dir, pm)
    output = {
        "command": command,
        "exit_code": result["exit_code"],
        "stdout": result["stdout"],
        "stderr": result["stderr"],
        "cwd": working_dir,
    }
    from zeus.security.audit import get_audit_logger
    get_audit_logger().log_execution(tool="run_terminal", command=command, result=output)
    return output


def run_background_command(command: str, cwd: Optional[str] = None) -> Dict[str, Any]:
    """Start a long-running shell command in the background and return its command_id."""
    from zeus.security.rate_limit import get_execution_limiter
    from zeus.tools.sandbox_client import current_user_session

    pm = _permissions()

    limiter = get_execution_limiter()
    user_id, session_id = current_user_session()
    if not limiter.is_allowed("run_terminal", user_id=user_id, session_id=session_id):
        return {"error": "Rate limit exceeded for run_background_command. Try again later."}

    if not pm.can_run_terminal():
        return {"error": pm.denied_message("run_terminal")}

    if pm.is_confirmation_required("run_background_command", {"command": command}):
        if not pm.confirm_tool("run_background_command", {"command": command}):
            return {"error": "Execution denied by user / Execução negada pelo usuário."}

    working_dir = None
    if cwd:
        working_dir = str(Path(cwd).expanduser().resolve())
        if not Path(working_dir).exists():
            return {"error": f"Working directory does not exist: {cwd}"}

    # Handle sudo: rewrite to `sudo -S` and feed the password on stdin so the
    # command does not fail with "a password is required" when run non-interactively.
    run_command = command
    password: Optional[str] = None
    if _needs_sudo(command):
        password = pm.ask_password(
            f"O comando requer sudo:\n  {command}",
            cache_key="sudo",
        )
        if password is None:
            return {"error": "Sudo password not provided / senha sudo não fornecida."}
        run_command = _SUDO_RE.sub(r"\1sudo -S", command, count=1)

    cmd_id = f"cmd_{uuid.uuid4().hex[:8]}"
    popen_kwargs: Dict[str, Any] = {
        "shell": True,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "text": True,
        "bufsize": 1,
        "cwd": working_dir,
        "env": safe_environment(),
        "start_new_session": True,
    }
    if password is not None:
        popen_kwargs["stdin"] = subprocess.PIPE
    proc = subprocess.Popen(run_command, **popen_kwargs)
    if password is not None and proc.stdin is not None:
        try:
            proc.stdin.write(password + "\n")
            proc.stdin.flush()
        finally:
            proc.stdin.close()
            password = None

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
