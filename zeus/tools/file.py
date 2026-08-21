"""File read/write/search/edit tools."""

import difflib
import fnmatch
import re
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

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
        is_new = not file_path.exists()
        old_content = None
        if not is_new:
            try:
                old_content = file_path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                old_content = None

        file_path.write_text(content, encoding="utf-8")
        from zeus.security.audit import get_audit_logger
        get_audit_logger().log_file_mutation(action="write", path=file_path, allowed=True)

        res: Dict[str, Any] = {
            "status": "success",
            "action": "created" if is_new else "modified",
            "path": str(file_path),
            "bytes_written": len(content),
            "content": content,
            "message": f"Successfully {'created' if is_new else 'modified'} {file_path}",
        }

        if not is_new and old_content is not None:
            old_lines = old_content.splitlines(keepends=True)
            new_lines = content.splitlines(keepends=True)
            diff = list(difflib.unified_diff(old_lines, new_lines, fromfile=f"a/{file_path.name}", tofile=f"b/{file_path.name}"))
            res["diff"] = "".join(diff)
            res["old_content"] = old_content

        return res
    except Exception as e:
        return {"error": str(e)}


def replace_file_content(
    path: str,
    target_content: str,
    replacement_content: str,
    allow_multiple: bool = False,
) -> Dict[str, Any]:
    """Replace target content with replacement content in a file."""
    file_path = Path(path).expanduser().resolve()
    if not _permissions.can_write_file(file_path):
        try:
            _permissions.ensure_write_allowed(file_path)
        except PermissionRequired as e:
            from zeus.security.audit import get_audit_logger
            get_audit_logger().log_file_mutation(action="write", path=file_path, allowed=False)
            return {"permission_required": {"action": e.action, "path": str(e.path)}}

    if not file_path.exists() or not file_path.is_file():
        return {"error": f"File not found or not a valid file: {path}"}

    try:
        old_content = file_path.read_text(encoding="utf-8", errors="ignore")
        count = old_content.count(target_content)

        if count == 0:
            return {"error": f"Target content not found in {path}"}

        if count > 1 and not allow_multiple:
            return {"error": f"Target content found {count} times in {path}. Set allow_multiple=True to replace all occurrences."}

        new_content = old_content.replace(target_content, replacement_content, 1 if not allow_multiple else -1)
        file_path.write_text(new_content, encoding="utf-8")

        from zeus.security.audit import get_audit_logger
        get_audit_logger().log_file_mutation(action="write", path=file_path, allowed=True)

        old_lines = old_content.splitlines(keepends=True)
        new_lines = new_content.splitlines(keepends=True)
        diff = list(difflib.unified_diff(old_lines, new_lines, fromfile=f"a/{file_path.name}", tofile=f"b/{file_path.name}"))

        return {
            "status": "success",
            "action": "modified",
            "path": str(file_path),
            "replacements_made": count if allow_multiple else 1,
            "content": new_content,
            "old_content": old_content,
            "diff": "".join(diff),
            "message": f"Successfully replaced target content in {file_path}",
        }
    except Exception as e:
        return {"error": str(e)}


def move_file(src: str, dest: str) -> Dict[str, Any]:
    """Move or rename a file or directory from src to dest."""
    src_path = Path(src).expanduser().resolve()
    dest_path = Path(dest).expanduser().resolve()

    if not src_path.exists():
        return {"error": f"Source path not found: {src}"}

    if not _permissions.can_delete_file(src_path):
        try:
            _permissions.ensure_delete_allowed(src_path)
        except PermissionRequired as e:
            return {"permission_required": {"action": e.action, "path": str(e.path)}}

    if not _permissions.can_write_file(dest_path):
        try:
            _permissions.ensure_write_allowed(dest_path)
        except PermissionRequired as e:
            return {"permission_required": {"action": e.action, "path": str(e.path)}}

    try:
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src_path), str(dest_path))

        from zeus.security.audit import get_audit_logger
        get_audit_logger().log_file_mutation(action="move", path=dest_path, allowed=True)

        return {
            "status": "success",
            "action": "moved",
            "src": str(src_path),
            "dest": str(dest_path),
            "message": f"Successfully moved {src_path} to {dest_path}",
        }
    except Exception as e:
        return {"error": str(e)}


def copy_file(src: str, dest: str) -> Dict[str, Any]:
    """Copy a file or directory tree from src to dest."""
    src_path = Path(src).expanduser().resolve()
    dest_path = Path(dest).expanduser().resolve()

    if not src_path.exists():
        return {"error": f"Source path not found: {src}"}

    if not _permissions.can_write_file(dest_path):
        try:
            _permissions.ensure_write_allowed(dest_path)
        except PermissionRequired as e:
            return {"permission_required": {"action": e.action, "path": str(e.path)}}

    try:
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        if src_path.is_dir():
            shutil.copytree(str(src_path), str(dest_path), dirs_exist_ok=True)
        else:
            shutil.copy2(str(src_path), str(dest_path))

        from zeus.security.audit import get_audit_logger
        get_audit_logger().log_file_mutation(action="copy", path=dest_path, allowed=True)

        return {
            "status": "success",
            "action": "copied",
            "src": str(src_path),
            "dest": str(dest_path),
            "message": f"Successfully copied {src_path} to {dest_path}",
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


def grep_search(
    query: str,
    path: str = ".",
    case_insensitive: bool = True,
    includes: Optional[List[str]] = None,
    max_results: int = 50,
) -> Dict[str, Any]:
    """Perform exact text or regex search across files in path."""
    dir_path = Path(path).expanduser().resolve()
    if not _permissions.can_list_directory(dir_path):
        return {"error": "Directory search not allowed at current permission level."}

    flags = re.IGNORECASE if case_insensitive else 0
    try:
        regex = re.compile(query, flags)
    except re.error as e:
        return {"error": f"Invalid regex pattern: {e}"}

    matches: List[Dict[str, Any]] = []
    try:
        for file_path in dir_path.rglob("*"):
            if not file_path.is_file():
                continue

            parts = file_path.parts
            if any(p in (".git", "__pycache__", ".venv", "node_modules", ".pytest_cache") for p in parts):
                continue

            if includes:
                if not any(fnmatch.fnmatch(file_path.name, pat) or fnmatch.fnmatch(str(file_path), pat) for pat in includes):
                    continue

            try:
                text = file_path.read_text(encoding="utf-8", errors="ignore")
                for line_num, line in enumerate(text.splitlines(), 1):
                    if regex.search(line):
                        matches.append({
                            "path": str(file_path),
                            "line": line_num,
                            "content": line.strip()[:200],
                        })
                        if len(matches) >= max_results:
                            break
            except Exception:
                continue

            if len(matches) >= max_results:
                break

        return {
            "status": "success",
            "query": query,
            "path": str(dir_path),
            "total_matches": len(matches),
            "matches": matches,
        }
    except Exception as e:
        return {"error": str(e)}


def search_files(pattern: str, path: str = ".") -> Dict[str, Any]:
    return grep_search(query=pattern, path=path)


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
    name="replace_file_content",
    description="Replace target content with new content in an existing file (generates diff).",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "target_content": {"type": "string"},
            "replacement_content": {"type": "string"},
            "allow_multiple": {"type": "boolean", "default": False},
        },
        "required": ["path", "target_content", "replacement_content"],
    },
    handler=replace_file_content,
    tags=["file", "write"],
)

register_tool(
    name="move_file",
    description="Move or rename a file or directory from src to dest.",
    parameters={
        "type": "object",
        "properties": {
            "src": {"type": "string"},
            "dest": {"type": "string"},
        },
        "required": ["src", "dest"],
    },
    handler=move_file,
    tags=["file", "write", "delete"],
)

register_tool(
    name="copy_file",
    description="Copy a file or directory tree from src to dest.",
    parameters={
        "type": "object",
        "properties": {
            "src": {"type": "string"},
            "dest": {"type": "string"},
        },
        "required": ["src", "dest"],
    },
    handler=copy_file,
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
    name="grep_search",
    description="Perform high-speed regex search across project files.",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "path": {"type": "string", "default": "."},
            "case_insensitive": {"type": "boolean", "default": True},
            "includes": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional list of glob patterns e.g. ['*.py']",
            },
            "max_results": {"type": "integer", "default": 50},
        },
        "required": ["query"],
    },
    handler=grep_search,
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
