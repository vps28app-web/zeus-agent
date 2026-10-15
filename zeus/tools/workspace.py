"""Session workspace management for the local Zeus CLI."""

import os
from pathlib import Path
from typing import Any, Dict

from zeus.core.registry import register_tool


def change_working_directory(path: str) -> Dict[str, Any]:
    """Change the local CLI process cwd and project-only permission boundary."""
    if os.getenv("ZEUS_LOCAL_CLI") != "1":
        return {"error": "Workspace switching is available only in the local Zeus CLI."}

    if not path or not path.strip():
        return {"error": "A target directory is required."}

    try:
        target = Path(path).expanduser().resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        return {"error": f"Cannot resolve directory '{path}': {exc}"}

    if not target.is_dir():
        return {"error": f"Not a directory: {target}"}

    try:
        from zeus.security.permissions import get_global_permission_manager
        from zeus.tools.code_intel import _permissions as code_intel_permissions
        from zeus.tools.file import get_file_permission_manager

        managers = [
            get_global_permission_manager(),
            get_file_permission_manager(),
            code_intel_permissions,
        ]
        os.chdir(target)
        os.environ["ZEUS_PROJECT_DIR"] = str(target)
        for manager in managers:
            manager.project_dir = target
    except OSError as exc:
        return {"error": f"Could not switch working directory to '{target}': {exc}"}

    return {
        "status": "success",
        "working_directory": str(target),
        "message": f"Working directory and project-only boundary changed to {target}",
    }


register_tool(
    name="change_working_directory",
    description=(
        "Change the active working directory and project_only file-access boundary for this local "
        "CLI session. Use only when the user explicitly asks to switch projects and provides the "
        "target directory. The change lasts for this process; it does not edit configuration files."
    ),
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Existing directory to use as the workspace."},
        },
        "required": ["path"],
    },
    handler=change_working_directory,
    required_env=["ZEUS_LOCAL_CLI"],
    tags=["workspace", "project", "terminal"],
)
