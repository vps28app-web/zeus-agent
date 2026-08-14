"""File read/write/search tools."""

import os
from pathlib import Path
from typing import Any, Dict, List

from zeus.core.registry import register_tool


def read_file(path: str, limit: int = 2000, offset: int = 1) -> Dict[str, Any]:
    file_path = Path(path).expanduser().resolve()
    if not file_path.exists():
        return {"error": f"File not found: {path}"}
    try:
        lines = file_path.read_text(encoding="utf-8").splitlines()
        start = max(0, offset - 1)
        end = start + limit
        return {
            "path": str(file_path),
            "total_lines": len(lines),
            "lines": lines[start:end],
        }
    except Exception as e:
        return {"error": str(e)}


def write_file(path: str, content: str) -> Dict[str, Any]:
    file_path = Path(path).expanduser().resolve()
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        return {"path": str(file_path), "bytes_written": len(content)}
    except Exception as e:
        return {"error": str(e)}


def list_directory(path: str = ".") -> Dict[str, Any]:
    dir_path = Path(path).expanduser().resolve()
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
)
