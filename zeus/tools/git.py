"""Git operations tool."""

import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from zeus.core.registry import register_tool


def _run_git(args: List[str], cwd: Optional[str] = None, timeout: int = 60) -> Dict[str, Any]:
    """Run a git command and return structured output."""
    command = ["git"] + args
    work_dir = Path(cwd).expanduser().resolve() if cwd else None
    try:
        result = subprocess.run(
            command,
            cwd=work_dir,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "command": " ".join(command),
            "cwd": str(work_dir) if work_dir else None,
            "exit_code": result.returncode,
            "stdout": result.stdout[:8000],
            "stderr": result.stderr[:4000],
            "success": result.returncode == 0,
        }
    except subprocess.TimeoutExpired:
        return {"error": "Git command timed out", "command": " ".join(command)}
    except FileNotFoundError:
        return {"error": "git not found in PATH"}
    except Exception as e:
        return {"error": str(e)}


def git_status(repo_path: str = ".") -> Dict[str, Any]:
    """Show working tree status."""
    return _run_git(["status", "--short", "--branch"], cwd=repo_path)


def git_log(repo_path: str = ".", max_count: int = 10, oneline: bool = True) -> Dict[str, Any]:
    """Show commit log."""
    args = ["log", f"--max-count={max_count}"]
    if oneline:
        args.append("--oneline")
    args.append("--decorate")
    return _run_git(args, cwd=repo_path)


def git_diff(repo_path: str = ".", staged: bool = False, target: Optional[str] = None) -> Dict[str, Any]:
    """Show changes between commits, commit and working tree, etc."""
    args = ["diff"]
    if staged:
        args.append("--cached")
    if target:
        args.append(target)
    return _run_git(args, cwd=repo_path)


def git_branch(repo_path: str = ".", all_branches: bool = False) -> Dict[str, Any]:
    """List branches."""
    args = ["branch", "--show-current"] if not all_branches else ["branch", "-a"]
    return _run_git(args, cwd=repo_path)


def git_checkout(repo_path: str = ".", branch: str = "") -> Dict[str, Any]:
    """Switch branches or restore working tree files."""
    if not branch:
        return {"error": "branch is required"}
    return _run_git(["checkout", branch], cwd=repo_path)


def git_pull(repo_path: str = ".", remote: str = "origin", branch: Optional[str] = None) -> Dict[str, Any]:
    """Fetch from and integrate with another repository."""
    args = ["pull", remote]
    if branch:
        args.append(branch)
    return _run_git(args, cwd=repo_path)


def git_push(repo_path: str = ".", remote: str = "origin", branch: Optional[str] = None) -> Dict[str, Any]:
    """Update remote refs along with associated objects."""
    args = ["push", remote]
    if branch:
        args.append(branch)
    return _run_git(args, cwd=repo_path)


def git_commit(repo_path: str = ".", message: str = "", add_all: bool = False) -> Dict[str, Any]:
    """Record changes to the repository."""
    if not message:
        return {"error": "commit message is required"}
    if add_all:
        stage = _run_git(["add", "-A"], cwd=repo_path)
        if not stage.get("success"):
            return stage
    return _run_git(["commit", "-m", message], cwd=repo_path)


def git_clone(repo_url: str, target_path: Optional[str] = None, depth: Optional[int] = None) -> Dict[str, Any]:
    """Clone a repository into a new directory."""
    args = ["clone"]
    if depth:
        args.extend(["--depth", str(depth)])
    args.append(repo_url)
    if target_path:
        args.append(target_path)
    return _run_git(args)


register_tool(
    name="git_status",
    description="Show the working tree status of a git repository.",
    parameters={
        "type": "object",
        "properties": {
            "repo_path": {"type": "string", "default": ".", "description": "Path to the git repository."},
        },
        "required": [],
    },
    handler=git_status,
    tags=["git", "read"],
)

register_tool(
    name="git_log",
    description="Show the commit log of a git repository.",
    parameters={
        "type": "object",
        "properties": {
            "repo_path": {"type": "string", "default": "."},
            "max_count": {"type": "integer", "default": 10},
            "oneline": {"type": "boolean", "default": True},
        },
        "required": [],
    },
    handler=git_log,
    tags=["git", "read"],
)

register_tool(
    name="git_diff",
    description="Show changes in a git repository.",
    parameters={
        "type": "object",
        "properties": {
            "repo_path": {"type": "string", "default": "."},
            "staged": {"type": "boolean", "default": False},
            "target": {"type": "string", "description": "Optional commit, branch, or file to diff."},
        },
        "required": [],
    },
    handler=git_diff,
    tags=["git", "read"],
)

register_tool(
    name="git_branch",
    description="List branches in a git repository.",
    parameters={
        "type": "object",
        "properties": {
            "repo_path": {"type": "string", "default": "."},
            "all_branches": {"type": "boolean", "default": False},
        },
        "required": [],
    },
    handler=git_branch,
    tags=["git", "read"],
)

register_tool(
    name="git_checkout",
    description="Switch to a branch in a git repository.",
    parameters={
        "type": "object",
        "properties": {
            "repo_path": {"type": "string", "default": "."},
            "branch": {"type": "string", "description": "Branch name to checkout."},
        },
        "required": ["branch"],
    },
    handler=git_checkout,
    tags=["git", "write"],
)

register_tool(
    name="git_pull",
    description="Pull changes from a remote repository.",
    parameters={
        "type": "object",
        "properties": {
            "repo_path": {"type": "string", "default": "."},
            "remote": {"type": "string", "default": "origin"},
            "branch": {"type": "string"},
        },
        "required": [],
    },
    handler=git_pull,
    tags=["git", "write"],
)

register_tool(
    name="git_push",
    description="Push local commits to a remote repository.",
    parameters={
        "type": "object",
        "properties": {
            "repo_path": {"type": "string", "default": "."},
            "remote": {"type": "string", "default": "origin"},
            "branch": {"type": "string"},
        },
        "required": [],
    },
    handler=git_push,
    tags=["git", "write"],
)

register_tool(
    name="git_commit",
    description="Commit staged changes with a message.",
    parameters={
        "type": "object",
        "properties": {
            "repo_path": {"type": "string", "default": "."},
            "message": {"type": "string", "description": "Commit message."},
            "add_all": {"type": "boolean", "default": False, "description": "Run git add -A before committing."},
        },
        "required": ["message"],
    },
    handler=git_commit,
    tags=["git", "write"],
)

register_tool(
    name="git_clone",
    description="Clone a remote git repository.",
    parameters={
        "type": "object",
        "properties": {
            "repo_url": {"type": "string", "description": "URL of the git repository."},
            "target_path": {"type": "string", "description": "Local directory to clone into."},
            "depth": {"type": "integer", "description": "Create a shallow clone with limited history."},
        },
        "required": ["repo_url"],
    },
    handler=git_clone,
    tags=["git", "write"],
)
