"""File read/write/search tools."""

from pathlib import Path
from typing import Any, Dict, List

from zeus.core.registry import register_tool
from zeus.security.permissions import PermissionManager, PermissionRequired

# Default permission manager. CLI/gateways can inject one with a callback.
_permissions = PermissionManager()


def set_file_permission_manager(pm: PermissionManager) -> None:
    """Allow CLI/gateway to inject a configured PermissionManager."""
    global _permissions
    _permissions = pm


def get_file_permission_manager() -> PermissionManager:
    """Get the active PermissionManager instance."""
    return _permissions


def set_file_permission_callback(callback):
    """Allow CLI/gateway to set a confirmation callback for interactive use."""
    global _permissions
    _permissions = PermissionManager(confirm_callback=callback)


def read_file(path: str, limit: int = 2000, offset: int = 1) -> Dict[str, Any]:
    file_path = Path(path).expanduser().resolve()
    if not _permissions.can_read_file(file_path):
        return {"error": "File read not allowed at current permission level."}
    if not file_path.exists():
        return {"error": f"File not found: {path}"}
    try:
        lines = file_path.read_text(encoding="utf-8").splitlines()
        start = max(0, offset - 1)
        end = start + limit
        selected = lines[start:end]
        return {
            "status": "success",
            "path": str(file_path),
            "total_lines": len(lines),
            "lines": selected,
            "message": f"Read {len(selected)} lines from {file_path}",
        }
    except Exception as e:
        return {"error": str(e)}


def write_file(path: str, content: str) -> Dict[str, Any]:
    file_path = Path(path).expanduser().resolve()
    if not _permissions.can_write_file(file_path):
        try:
            _permissions.ensure_write_allowed(file_path)
        except PermissionRequired as e:
            from zeus.security.audit import get_audit_logger
            get_audit_logger().log_file_mutation(action="write", path=file_path, allowed=False)
            return {"permission_required": {"action": e.action, "path": str(e.path)}}
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        from zeus.security.audit import get_audit_logger
        get_audit_logger().log_file_mutation(action="write", path=file_path, allowed=True)
        return {
            "status": "success",
            "path": str(file_path),
            "bytes_written": len(content),
            "message": f"Successfully wrote {len(content)} bytes to {file_path}",
        }
    except Exception as e:
        return {"error": str(e)}


def delete_file(path: str) -> Dict[str, Any]:
    file_path = Path(path).expanduser().resolve()
    if not _permissions.can_delete_file(file_path):
        try:
            _permissions.ensure_delete_allowed(file_path)
        except PermissionRequired as e:
            from zeus.security.audit import get_audit_logger
            get_audit_logger().log_file_mutation(action="delete", path=file_path, allowed=False)
            return {"permission_required": {"action": e.action, "path": str(e.path)}}
    try:
        if file_path.is_file():
            file_path.unlink()
            from zeus.security.audit import get_audit_logger
            get_audit_logger().log_file_mutation(action="delete", path=file_path, allowed=True)
            return {
                "status": "success",
                "deleted": True,
                "path": str(file_path),
                "message": f"Successfully deleted {file_path}",
            }
        return {"error": f"Not a file: {path}"}
    except Exception as e:
        return {"error": str(e)}



def list_directory(path: str = ".") -> Dict[str, Any]:
    dir_path = Path(path).expanduser().resolve()
    if not _permissions.can_list_directory(dir_path):
        return {"error": "Directory listing not allowed at current permission level."}
    try:
        entries = []
        for entry in dir_path.iterdir():
            entries.append({
                "name": entry.name,
                "type": "directory" if entry.is_dir() else "file",
                "size": entry.stat().st_size if entry.is_file() else None,
            })
        return {"path": str(dir_path), "entries": entries}
    except Exception as e:
        return {"error": str(e)}


def search_files(pattern: str, path: str = ".") -> Dict[str, Any]:
    import re

    dir_path = Path(path).expanduser().resolve()
    if not _permissions.can_list_directory(dir_path):
        return {"error": "Directory search not allowed at current permission level."}
    matches: List[Dict[str, Any]] = []
    try:
        for file_path in dir_path.rglob("*"):
            if file_path.is_file():
                try:
                    text = file_path.read_text(encoding="utf-8", errors="ignore")
                    for i, line in enumerate(text.splitlines(), 1):
                        if re.search(pattern, line):
                            matches.append({"path": str(file_path), "line": i, "content": line[:200]})
                            if len(matches) >= 50:
                                break
                    if len(matches) >= 50:
                        break
                except Exception:
                    continue
        return {"pattern": pattern, "path": str(dir_path), "matches": matches}
    except Exception as e:
        return {"error": str(e)}


register_tool(
    name="read_file",
    description="Read lines from a text file.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "limit": {"type": "integer", "default": 2000},
            "offset": {"type": "integer", "default": 1},
        },
        "required": ["path"],
    },
    handler=read_file,
    tags=["file", "read"],
)

register_tool(
    name="write_file",
    description="Write content to a file (creates parent directories).",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "content": {"type": "string"},
        },
        "required": ["path", "content"],
    },
    handler=write_file,
    tags=["file", "write"],
)

register_tool(
    name="delete_file",
    description="Delete a file.",
    parameters={
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
    },
    handler=delete_file,
    tags=["file", "delete"],
)

register_tool(
    name="list_directory",
    description="List files and directories in a path.",
    parameters={
        "type": "object",
        "properties": {"path": {"type": "string", "default": "."}},
        "required": [],
    },
    handler=list_directory,
    tags=["file", "read"],
)

register_tool(
    name="search_files",
    description="Search file contents with a regex pattern.",
    parameters={
        "type": "object",
        "properties": {
            "pattern": {"type": "string"},
            "path": {"type": "string", "default": "."},
        },
        "required": ["pattern"],
    },
    handler=search_files,
    tags=["file", "read"],
)
