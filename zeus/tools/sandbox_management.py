"""Sandbox lifecycle management: restart the Go sandbox server when needed."""

import os
import shutil
import signal
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from zeus.core.registry import register_tool
from zeus.tools.sandbox_client import DEFAULT_URL, is_sandbox_available

SANBOX_BINARY = Path(__file__).resolve().parents[2] / "sandbox" / "sandbox"


def _find_sandbox_processes() -> List[Dict[str, Any]]:
    """Find running sandbox server processes owned by root or current user."""
    procs = []
    try:
        result = subprocess.run(
            ["ps", "aux"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        for line in result.stdout.splitlines():
            if "sandbox/sandbox" in line and "grep" not in line:
                parts = line.split(None, 10)
                if len(parts) >= 2:
                    procs.append({
                        "pid": int(parts[1]),
                        "user": parts[0],
                        "cmd": parts[10] if len(parts) > 10 else "",
                    })
    except Exception:
        pass
    return procs


def _kill_process(pid: int, sudo_password: Optional[str] = None) -> Dict[str, Any]:
    """Kill a process, escalating to sudo if needed."""
    # Try normal kill first.
    try:
        os.kill(pid, signal.SIGKILL)
        return {"success": True, "method": "direct"}
    except PermissionError:
        pass
    except ProcessLookupError:
        return {"success": True, "method": "already-dead"}

    # Need sudo. If we have a password, use sudo -S.
    if sudo_password:
        try:
            result = subprocess.run(
                ["sudo", "-S", "kill", "-9", str(pid)],
                input=sudo_password + "\n",
                capture_output=True,
                text=True,
                timeout=15,
            )
            if result.returncode == 0:
                return {"success": True, "method": "sudo-with-password"}
            return {"success": False, "error": f"sudo kill failed: {result.stderr.strip()}"}
        except Exception as e:
            return {"success": False, "error": f"sudo kill exception: {e}"}

    # No password provided: ask the user.
    return {
        "sudo_required": True,
        "message": f"Need sudo to kill sandbox process {pid}.",
        "pid": pid,
        "command": f"sudo kill -9 {pid}",
    }


def restart_sandbox(
    addr: Optional[str] = None,
    sudo_password: Optional[str] = None,
) -> Dict[str, Any]:
    """Restart the Go sandbox server, rebuilding from source if available.

    If the old sandbox is owned by root and cannot be killed directly,
    returns a sudo_required response so the CLI can prompt for a password
    securely (ghost/passwordless input) and retry.
    """
    target_addr = (addr or os.getenv("ZEUS_SANDBOX_URL", DEFAULT_URL)).rstrip("/")

    # Build fresh binary if source is present.
    binary_path = SANBOX_BINARY
    source_dir = binary_path.parent
    if (source_dir / "cmd" / "sandbox").exists():
        try:
            build = subprocess.run(
                ["go", "build", "-o", str(binary_path), "./cmd/sandbox"],
                cwd=str(source_dir),
                capture_output=True,
                text=True,
                timeout=120,
            )
            if build.returncode != 0:
                return {
                    "error": f"Sandbox build failed: {build.stderr.strip()}",
                    "stdout": build.stdout,
                }
        except Exception as e:
            return {"error": f"Failed to build sandbox: {e}"}

    if not binary_path.exists():
        return {"error": f"Sandbox binary not found: {binary_path}"}

    # Kill existing sandbox processes.
    old_procs = _find_sandbox_processes()
    for proc in old_procs:
        kill_res = _kill_process(proc["pid"], sudo_password=sudo_password)
        if kill_res.get("sudo_required"):
            return {
                "sudo_required": True,
                "message": kill_res["message"],
                "pid": kill_res["pid"],
                "command": kill_res["command"],
            }
        if not kill_res.get("success"):
            return {"error": f"Failed to kill old sandbox {proc['pid']}: {kill_res.get('error')}"}

    # Wait for port to be free.
    for _ in range(10):
        if not _port_in_use(target_addr):
            break
        time.sleep(0.5)
    else:
        return {"error": f"Port for {target_addr} still in use after killing old processes."}

    # Start new sandbox in background.
    try:
        proc = subprocess.Popen(
            [str(binary_path), "-addr", target_addr.replace("http://", "")],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception as e:
        return {"error": f"Failed to start sandbox: {e}"}

    # Wait for health check.
    for _ in range(20):
        if is_sandbox_available(target_addr):
            return {
                "success": True,
                "pid": proc.pid,
                "addr": target_addr,
                "rebuilt": True,
            }
        time.sleep(0.5)

    return {"error": f"Sandbox started (pid {proc.pid}) but health check failed at {target_addr}"}


def _port_in_use(addr: str) -> bool:
    """Check whether the address/port is currently listening."""
    host_port = addr.replace("http://", "").replace("https://", "")
    if ":" not in host_port:
        host_port += ":9876"
    _, port = host_port.rsplit(":", 1)
    try:
        result = subprocess.run(
            ["ss", "-tln"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return f":{port} " in result.stdout
    except Exception:
        return False


def sandbox_status() -> Dict[str, Any]:
    """Report whether the sandbox server is running and reachable."""
    addr = os.getenv("ZEUS_SANDBOX_URL", DEFAULT_URL).rstrip("/")
    procs = _find_sandbox_processes()
    available = is_sandbox_available(addr)
    return {
        "addr": addr,
        "reachable": available,
        "processes": procs,
    }


register_tool(
    name="restart_sandbox",
    description=(
        "Restart the Zeus Go sandbox server. Use when sandbox commands return 403, "
        "connection errors, or binary whitelist errors. May ask for sudo password if the "
        "old process is owned by root."
    ),
    parameters={
        "type": "object",
        "properties": {
            "addr": {
                "type": "string",
                "description": "Optional sandbox address (default: http://127.0.0.1:9876).",
            },
            "sudo_password": {
                "type": "string",
                "description": "Sudo password for killing root-owned sandbox. Prefer empty; the CLI will prompt securely.",
            },
        },
    },
    handler=restart_sandbox,
    tags=["sandbox", "system", "terminal"],
)

register_tool(
    name="sandbox_status",
    description="Check whether the Zeus sandbox server is running and reachable.",
    parameters={
        "type": "object",
        "properties": {},
    },
    handler=sandbox_status,
    tags=["sandbox", "system"],
)
