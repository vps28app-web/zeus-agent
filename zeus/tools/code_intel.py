"""Code Intelligence & AST Symbol Mapping Tools."""

import ast
import os
from pathlib import Path
import re
from typing import Any, Dict, List, Optional

from zeus.core.registry import register_tool
from zeus.security.permissions import PermissionManager

_permissions = PermissionManager()


def _parse_python_ast(source_code: str, file_path: str) -> Dict[str, Any]:
    """Parse Python source code using AST and return classes, functions, docstrings, and imports."""
    try:
        tree = ast.parse(source_code)
    except Exception as e:
        return {"error": f"AST parse error in {file_path}: {e}"}

    imports = []
    classes = []
    functions = []

    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            for alias in node.names:
                imports.append(f"{mod}.{alias.name}" if mod else alias.name)
        elif isinstance(node, ast.ClassDef):
            methods = []
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    args = [a.arg for a in item.args.args]
                    methods.append({
                        "name": item.name,
                        "line": item.lineno,
                        "end_line": getattr(item, "end_lineno", item.lineno),
                        "args": args,
                        "docstring": ast.get_docstring(item),
                    })
            classes.append({
                "name": node.name,
                "line": node.lineno,
                "end_line": getattr(node, "end_lineno", node.lineno),
                "bases": [ast.unparse(b) for b in node.bases] if hasattr(ast, "unparse") else [],
                "docstring": ast.get_docstring(node),
                "methods": methods,
            })
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = [a.arg for a in node.args.args]
            functions.append({
                "name": node.name,
                "line": node.lineno,
                "end_line": getattr(node, "end_lineno", node.lineno),
                "args": args,
                "docstring": ast.get_docstring(node),
            })

    return {
        "file": file_path,
        "imports": imports,
        "classes": classes,
        "functions": functions,
    }


def parse_code_structure(path: str) -> Dict[str, Any]:
    """Inspect AST structure (classes, methods, functions, docstrings) of a code file."""
    file_path = Path(path).expanduser().resolve()
    if not _permissions.can_read_file(file_path):
        return {"error": "File read not allowed at current permission level."}
    if not file_path.exists() or not file_path.is_file():
        return {"error": f"File not found: {path}"}

    try:
        content = file_path.read_text(encoding="utf-8", errors="ignore")
        if file_path.suffix == ".py":
            return _parse_python_ast(content, str(file_path))

        # Fallback regex parser for non-python files (JS/TS/Go/Rust/C)
        functions = []
        classes = []
        lines = content.splitlines()
        for idx, line in enumerate(lines, 1):
            fn_match = re.search(r'(?:function|def|fn|const|let|var)\s+([a-zA-Z0-9_]+)\s*[\(=]', line)
            if fn_match:
                functions.append({"name": fn_match.group(1), "line": idx, "content": line.strip()[:100]})
            cls_match = re.search(r'class\s+([a-zA-Z0-9_]+)', line)
            if cls_match:
                classes.append({"name": cls_match.group(1), "line": idx, "content": line.strip()[:100]})

        return {
            "file": str(file_path),
            "classes": classes,
            "functions": functions,
        }
    except Exception as e:
        return {"error": str(e)}


def codebase_symbol_map(path: str = ".", max_files: int = 100) -> Dict[str, Any]:
    """Build a comprehensive Symbol Map (Repo Map) of all code definitions in the workspace."""
    dir_path = Path(path).expanduser().resolve()
    if not _permissions.can_list_directory(dir_path):
        return {"error": "Directory access not allowed at current permission level."}

    summary: List[Dict[str, Any]] = []
    scanned_files = 0

    try:
        for file_path in sorted(dir_path.rglob("*")):
            if not file_path.is_file():
                continue

            parts = file_path.parts
            if any(p in (".git", "__pycache__", ".venv", "node_modules", ".pytest_cache", "dist", "build") for p in parts):
                continue

            if file_path.suffix not in (".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs", ".java", ".c", ".cpp"):
                continue

            try:
                rel_path = file_path.relative_to(dir_path)
            except Exception:
                rel_path = file_path

            struct = parse_code_structure(str(file_path))
            if "error" not in struct:
                scanned_files += 1
                cls_names = [c["name"] for c in struct.get("classes", [])]
                fn_names = [f["name"] for f in struct.get("functions", [])]
                if cls_names or fn_names:
                    summary.append({
                        "path": str(rel_path),
                        "classes": cls_names,
                        "functions": fn_names,
                    })

            if scanned_files >= max_files:
                break

        return {
            "status": "success",
            "root_path": str(dir_path),
            "files_scanned": scanned_files,
            "symbol_map": summary,
        }
    except Exception as e:
        return {"error": str(e)}


def find_symbol(name: str, path: str = ".") -> Dict[str, Any]:
    """Find the exact file location, line range, and docstring of a class or function symbol."""
    dir_path = Path(path).expanduser().resolve()
    if not _permissions.can_list_directory(dir_path):
        return {"error": "Directory access not allowed at current permission level."}

    matches: List[Dict[str, Any]] = []

    try:
        for file_path in dir_path.rglob("*.py"):
            if not file_path.is_file():
                continue
            parts = file_path.parts
            if any(p in (".git", "__pycache__", ".venv", "node_modules", ".pytest_cache") for p in parts):
                continue

            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
                parsed = _parse_python_ast(content, str(file_path))
                if "error" in parsed:
                    continue

                for fn in parsed.get("functions", []):
                    if fn["name"].lower() == name.lower():
                        matches.append({
                            "type": "function",
                            "name": fn["name"],
                            "file": str(file_path),
                            "line": fn["line"],
                            "end_line": fn["end_line"],
                            "args": fn.get("args", []),
                            "docstring": fn.get("docstring"),
                        })

                for cls in parsed.get("classes", []):
                    if cls["name"].lower() == name.lower():
                        matches.append({
                            "type": "class",
                            "name": cls["name"],
                            "file": str(file_path),
                            "line": cls["line"],
                            "end_line": cls["end_line"],
                            "docstring": cls.get("docstring"),
                        })
                    for m in cls.get("methods", []):
                        if m["name"].lower() == name.lower():
                            matches.append({
                                "type": "method",
                                "name": f"{cls['name']}.{m['name']}",
                                "file": str(file_path),
                                "line": m["line"],
                                "end_line": m["end_line"],
                                "args": m.get("args", []),
                                "docstring": m.get("docstring"),
                            })
            except Exception:
                continue

        return {
            "status": "success",
            "query_symbol": name,
            "total_matches": len(matches),
            "matches": matches,
        }
    except Exception as e:
        return {"error": str(e)}


register_tool(
    name="parse_code_structure",
    description="Inspect AST structure (classes, methods, functions, docstrings) of a code file.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Target source file path."},
        },
        "required": ["path"],
    },
    handler=parse_code_structure,
    tags=["code", "read"],
)

register_tool(
    name="codebase_symbol_map",
    description="Build an instant Repo Symbol Map of all code classes and functions across the project.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Root directory path.", "default": "."},
            "max_files": {"type": "integer", "description": "Max files to scan.", "default": 100},
        },
        "required": [],
    },
    handler=codebase_symbol_map,
    tags=["code", "read"],
)

register_tool(
    name="find_symbol",
    description="Find the exact file, line numbers, parameters and docstring of a class/function symbol.",
    parameters={
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Class or function name to locate."},
            "path": {"type": "string", "description": "Search root directory.", "default": "."},
        },
        "required": ["name"],
    },
    handler=find_symbol,
    tags=["code", "read"],
)
