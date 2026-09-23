"""SSH execution tool with optional password support.

Runs a command on a remote host. Prefers key-based auth (no password);
if that fails and no password is provided, it returns an ssh_password_required
response so the CLI can prompt the user for the password securely (ghost input)
and retry using sshpass.
"""

import os
import shutil
import subprocess
from typing import Any, Dict, Optional

from zeus.core.registry import register_tool


def _find_sshpass() -> Optional[str]:
    """Locate sshpass on PATH, preferring user-local installs."""
    sshpass = shutil.which("sshpass")
    if sshpass:
        return sshpass
    local = os.path.expanduser("~/.local/bin/sshpass")
    if os.path.isfile(local) and os.access(local, os.X_OK):
        return local
    return None


def ssh_run(
    host: str,
    command: str,
    user: Optional[str] = None,
    port: int = 22,
    password: Optional[str] = None,
    timeout: int = 60,
) -> Dict[str, Any]:
    """Run a command on a remote host over SSH.

    Prefers key-based auth. If that fails and no password is given, returns
    ssh_password_required so the CLI can prompt securely.
    """
    host = host.strip()
    if not host:
        return {"error": "host is required"}
    if not command.strip():
        return {"error": "command is required"}

    # Support "user@host" format: extract the user from the host string if
    # the user argument was not provided explicitly.
    if not user and "@" in host:
        user, host = host.rsplit("@", 1)
        user = user.strip() or None
        host = host.strip()

    # If we still don't know the user, ask the CLI to prompt for it instead of
    # guessing (which would fail auth and waste attempts).
    if not user:
        return {
            "ssh_user_required": True,
            "message": (
                f"No SSH user was specified for host {host} (port {port}). "
                "Ask the user for the SSH username."
            ),
            "host": host,
            "port": port,
            "command": command,
        }

    target = f"{user}@{host}"
    ssh_cmd = [
        "ssh",
        "-p", str(port),
        "-o", "BatchMode=yes",
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", "ConnectTimeout=15",
        target,
        command,
    ]

    # Try key-based auth first (no password).
    try:
        result = subprocess.run(
            ssh_cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode == 0:
            return {
                "host": host,
                "user": user,
                "exit_code": result.returncode,
                "stdout": result.stdout[:8000],
                "stderr": result.stderr[:4000],
                "auth": "key",
            }
        # Key auth failed. If we have no password to fall back on, ask for it.
        if not password:
            return {
                "ssh_password_required": True,
                "message": (
                    f"SSH key auth failed for {target} (port {port}). "
                    "A password is required."
                ),
                "host": host,
                "user": user,
                "port": port,
                "command": command,
            }
    except subprocess.TimeoutExpired:
        return {"error": f"SSH connection to {target} timed out after {timeout}s"}
    except Exception as e:
        return {"error": f"SSH failed: {e}"}

    # Password path: requires sshpass.
    sshpass = _find_sshpass()
    if not sshpass:
        return {
            "error": (
                "sshpass is not installed, so password auth is unavailable. "
                "Install it with: apt-get install sshpass"
            )
        }

    pass_cmd = [
        sshpass, "-p", password,
        "ssh",
        "-p", str(port),
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", "ConnectTimeout=15",
        target,
        command,
    ]
    try:
        result = subprocess.run(
            pass_cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "host": host,
            "user": user,
            "exit_code": result.returncode,
            "stdout": result.stdout[:8000],
            "stderr": result.stderr[:4000],
            "auth": "password",
        }
    except subprocess.TimeoutExpired:
        return {"error": f"SSH connection to {target} timed out after {timeout}s"}
    except Exception as e:
        return {"error": f"SSH failed: {e}"}
    finally:
        # Clear password reference as soon as possible.
        password = None


register_tool(
    name="ssh_run",
    description=(
        "Run a command on a remote host over SSH. Prefers SSH key auth; "
        "falls back to asking for a password securely if key auth fails. "
        "Always pass the SSH user explicitly (e.g. user='valdeir28'), or put it "
        "in the host as 'user@host'."
    ),
    parameters={
        "type": "object",
        "properties": {
            "host": {"type": "string", "description": "Remote host (IP or hostname). Accepts 'user@host'."},
            "command": {"type": "string", "description": "Command to run on the remote host."},
            "user": {"type": "string", "description": "SSH user (e.g. 'valdeir28'). Always provide it when known."},
            "port": {"type": "integer", "description": "SSH port.", "default": 22},
            "password": {
                "type": "string",
                "description": "SSH password. Prefer leaving empty; the CLI prompts securely.",
            },
            "timeout": {"type": "integer", "description": "Timeout in seconds.", "default": 60},
        },
        "required": ["host", "command"],
    },
    handler=ssh_run,
    tags=["ssh", "terminal", "remote", "execute"],
)
