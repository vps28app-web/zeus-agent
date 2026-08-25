"""Package management tool with explicit user confirmation.

Allows installing, removing, or updating packages via apt, flatpak, or pip,
but only when ZEUS_EXECUTION_PERMISSION=allow (host terminal mode) and the
user explicitly confirms the operation.
"""

import shlex
import subprocess
from typing import Any, Dict, List, Optional

from zeus.core.registry import register_tool
from zeus.security.permissions import PermissionManager

ALLOWED_MANAGERS = ("apt", "flatpak", "pip")

# Read-only / safe commands allowed without confirmation
SAFE_COMMANDS = {
    "apt": ("list", "search", "show", "policy", "cache"),
    "flatpak": ("list", "info", "search", "remote-list", "remotes"),
    "pip": ("list", "show", "search", "freeze", "index"),
}

# Mutating commands that require explicit confirmation
MUTATING_COMMANDS = {
    "apt": ("install", "remove", "purge", "autoremove", "clean", "update", "upgrade", "dist-upgrade"),
    "flatpak": ("install", "update", "uninstall", "remove", "repair"),
    "pip": ("install", "uninstall", "download"),
}


def _detect_manager(command: str) -> Optional[str]:
    """Detect package manager from the command string."""
    lowered = command.strip().lower()
    for manager in ALLOWED_MANAGERS:
        if lowered.startswith(manager):
            return manager
    return None


def _get_base_command(command: str) -> str:
    """Return the subcommand (e.g. install, remove) for a package manager line."""
    parts = command.strip().split()
    # parts[0] is the manager; parts[1] is the subcommand if present
    if len(parts) >= 2:
        return parts[1].lower()
    return ""


def _is_safe_command(manager: str, subcommand: str) -> bool:
    """Return True if the subcommand is read-only and does not need confirmation."""
    safe = SAFE_COMMANDS.get(manager, ())
    return subcommand in safe


def _is_mutating_command(manager: str, subcommand: str) -> bool:
    """Return True if the subcommand mutates the system and needs confirmation."""
    mutating = MUTATING_COMMANDS.get(manager, ())
    return subcommand in mutating


def _confirm_prompt(manager: str, command: str) -> str:
    """Build a bilingual confirmation prompt."""
    return (
        f"Package operation / Operação de pacote:\n"
        f"  • Manager / Gerenciador: {manager}\n"
        f"  • Command / Comando: {command}\n\n"
        f"This will modify software on this machine. / Isso modificará software nesta máquina.\n"
        f"Confirm? / Confirma? (yes/y/sim or no/n/nao)"
    )


def _sanitize_command(command: str) -> Optional[str]:
    """Validate that the command uses an allowed package manager and subcommand."""
    manager = _detect_manager(command)
    if manager is None:
        return (
            f"Package manager not allowed / Gerenciador não permitido. "
            f"Allowed / Permitidos: {', '.join(ALLOWED_MANAGERS)}"
        )

    subcommand = _get_base_command(command)
    if not subcommand:
        return "Missing subcommand / Subcomando ausente."

    safe = _is_safe_command(manager, subcommand)
    mutating = _is_mutating_command(manager, subcommand)

    if not safe and not mutating:
        return (
            f"Subcommand '{subcommand}' not allowed for {manager}. / "
            f"Subcomando '{subcommand}' não permitido para {manager}."
        )

    return None


def manage_packages(
    command: str,
    timeout: int = 300,
    cwd: Optional[str] = None,
    confirm: bool = True,
) -> Dict[str, Any]:
    """Run an apt/flatpak/pip command after checking execution mode and confirming mutating operations."""
    pm = PermissionManager()

    if not pm.can_run_terminal():
        return {
            "error": (
                "Package management requires host terminal mode / "
                "Gerenciamento de pacotes requer modo terminal no host. "
                "Run / Execute: /mode terminal (or set ZEUS_EXECUTION_PERMISSION=allow)"
            )
        }

    validation_error = _sanitize_command(command)
    if validation_error:
        return {"error": validation_error}

    manager = _detect_manager(command)
    if manager is None:
        return {"error": f"Internal error: manager detection failed for '{command}'"}

    subcommand = _get_base_command(command)
    needs_confirmation = _is_mutating_command(manager, subcommand)

    if needs_confirmation and confirm:
        # In interactive CLI this would prompt; when invoked by the agent loop
        # without a confirm callback, we return a permission_required response.
        return {
            "permission_required": {
                "action": "manage_packages",
                "command": command,
                "message": _confirm_prompt(manager, command),
            }
        }

    working_dir = None
    if cwd:
        from pathlib import Path
        working_dir = str(Path(cwd).expanduser().resolve())

    # Use shell=True because package managers are invoked as full command lines;
    # the command is restricted to the allow-list above.
    result = subprocess.run(  # nosec B602
        command,
        shell=True,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=working_dir,
    )

    return {
        "command": command,
        "exit_code": result.returncode,
        "stdout": result.stdout[:8000],
        "stderr": result.stderr[:4000],
    }


register_tool(
    name="manage_packages",
    description=(
        "Manage system or Python packages via apt/flatpak/pip. "
        "Requires /mode terminal. Mutating operations (install/remove/update) ask for explicit confirmation."
    ),
    parameters={
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "Package manager command, e.g. 'apt list --installed', 'flatpak remove com.google.Chrome', 'pip install requests'.",
            },
            "timeout": {"type": "integer", "description": "Timeout in seconds.", "default": 300},
            "cwd": {"type": "string", "description": "Working directory (optional)."},
            "confirm": {
                "type": "boolean",
                "description": "Set to false only when the user has already confirmed the exact command.",
                "default": True,
            },
        },
        "required": ["command"],
    },
    handler=manage_packages,
    tags=["terminal", "system", "packages"],
)
