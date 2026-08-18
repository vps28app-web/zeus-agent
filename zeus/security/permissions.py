"""Permission manager for code, command, and file-system operations.

ZEUS_EXECUTION_PERMISSION levels:
- "deny": no code/shell execution allowed
- "sandbox_only": only sandboxed execute_python/execute_shell_script allowed
- "allow": full access including run_terminal on host

ZEUS_FILE_PERMISSION levels:
- "read_only": only read/list files; writes/deletes require user confirmation
- "project_only": read/write allowed only inside project dir without confirmation
- "unrestricted": full access without confirmation

Confirmed actions are persisted per session in memory and optionally per user in SQLite.
"""

import os
import re
import threading
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set


class PermissionRequired(Exception):
    """Raised when a file action requires explicit user confirmation."""

    def __init__(self, action: str, path: Path, message: str):
        self.action = action
        self.path = path
        self.message = message
        super().__init__(message)


class PermissionManager:
    """Centralized execution and file-system permission controls (thread-safe)."""

    EXEC_LEVELS = ("deny", "sandbox_only", "allow")
    FILE_LEVELS = ("read_only", "project_only", "unrestricted")

    def __init__(
        self,
        exec_level: Optional[str] = None,
        file_level: Optional[str] = None,
        project_dir: Optional[Path] = None,
        confirm_callback: Optional[Callable[[str], bool]] = None,
        user_id: Optional[str] = None,
    ):
        self.exec_level = (exec_level or os.getenv("ZEUS_EXECUTION_PERMISSION", "sandbox_only")).lower()
        if self.exec_level not in self.EXEC_LEVELS:
            self.exec_level = "sandbox_only"

        self.file_level = (file_level or os.getenv("ZEUS_FILE_PERMISSION", "read_only")).lower()
        if self.file_level not in self.FILE_LEVELS:
            self.file_level = "read_only"

        self.project_dir = (project_dir or Path(os.getenv("ZEUS_PROJECT_DIR", Path.cwd()))).resolve()
        self.confirm_callback = confirm_callback
        self.user_id = user_id or "anonymous"

        # In-memory session confirmations.
        self._confirmed_actions: Set[str] = set()
        self._once_confirmed_actions: Set[str] = set()
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Execution permissions
    # ------------------------------------------------------------------
    def can_run_terminal(self) -> bool:
        return self.exec_level == "allow"

    def can_run_sandboxed_shell(self) -> bool:
        return self.exec_level in ("sandbox_only", "allow")

    def can_run_sandboxed_python(self) -> bool:
        return self.exec_level in ("sandbox_only", "allow")

    def can_install_packages(self) -> bool:
        return self.exec_level in ("sandbox_only", "allow")

    def denied_message(self, action: str) -> str:
        return (
            f"Execution denied: {action} is not allowed at permission level '{self.exec_level}'. "
            f"Set ZEUS_EXECUTION_PERMISSION=allow to enable it."
        )

    # ------------------------------------------------------------------
    # File-system permissions
    # ------------------------------------------------------------------
    def _is_inside_project(self, path: Path) -> bool:
        """Return True if path is inside project_dir, guarding against traversal and symlinks."""
        try:
            resolved = path.resolve(strict=False)
            project = self.project_dir.resolve(strict=False)
            # Check via commonpath to prevent /project/../../etc/passwd
            common = Path(os.path.commonpath([resolved, project]))
            if common != project:
                return False
            # If the path exists, also check the real path (symlinks).
            if resolved.exists():
                real = resolved.resolve(strict=True)
                real_common = Path(os.path.commonpath([real, project]))
                if real_common != project:
                    return False
            return True
        except Exception:
            return False

    def can_read_file(self, path: Path) -> bool:
        return self.file_level in ("read_only", "project_only", "unrestricted")

    def can_list_directory(self, path: Path) -> bool:
        return self.file_level in ("read_only", "project_only", "unrestricted")

    def can_write_file(self, path: Path) -> bool:
        if self.file_level == "unrestricted":
            return True
        if self.file_level == "project_only":
            return self._is_inside_project(path)
        # read_only always requires confirmation.
        return False

    def can_delete_file(self, path: Path) -> bool:
        if self.file_level == "unrestricted":
            return True
        if self.file_level == "project_only":
            return self._is_inside_project(path)
        return False

    # ------------------------------------------------------------------
    # Persistent confirmation logic
    # ------------------------------------------------------------------
    def _confirm(self, message: str) -> bool:
        if self.confirm_callback:
            return self.confirm_callback(message)
        return False

    def _load_persistent_confirmations(self) -> Set[str]:
        """Load persisted confirmations from SQLite for this user."""
        try:
            from zeus.db.connection import init_db
            from zeus.db.repository import MemoryRepository

            init_db()
            repo = MemoryRepository()
            key = f"confirmed_actions:{self.user_id}"
            notes = repo.get(key)
            confirmations: Set[str] = set()
            for note in notes:
                for line in note.splitlines():
                    line = line.strip()
                    if line:
                        confirmations.add(line)
            return confirmations
        except Exception:
            return set()

    def _save_persistent_confirmation(self, action_key: str) -> None:
        """Persist a confirmation for this user."""
        try:
            from zeus.db.connection import init_db
            from zeus.db.repository import MemoryRepository

            init_db()
            repo = MemoryRepository()
            key = f"confirmed_actions:{self.user_id}"
            repo.add(key, action_key)
        except Exception:
            pass

    def grant_permission(
        self,
        action: str,
        path: Optional[Path] = None,
        scope: str = "once",
    ) -> None:
        """
        Grant permission for a file action.

        scope:
          - "once": allow once for this action and path
          - "always": remember for this session
          - "persist": remember across sessions (per user)
        """
        if path:
            action_key = f"{action}:{str(Path(path).resolve())}"
        else:
            action_key = f"{action}:*"
        category_key = f"{action}:*"

        with self._lock:
            if scope in ("always", "persist"):
                self._confirmed_actions.add(category_key)
                if scope == "persist":
                    self._save_persistent_confirmation(category_key)
            else:  # "once"
                self._once_confirmed_actions.add(action_key)

    def confirm_action(
        self,
        action: str,
        path: Path,
        scope: str = "once",
    ) -> bool:
        """
        Ask the user for permission to perform a file action.

        scope:
          - "once": only this operation
          - "always": remember for this session
          - "persist": remember across sessions (per user)
        """
        action_key = f"{action}:{str(path.resolve())}"
        category_key = f"{action}:*"

        with self._lock:
            if action_key in self._once_confirmed_actions:
                self._once_confirmed_actions.remove(action_key)
                return True

            if category_key in self._once_confirmed_actions:
                self._once_confirmed_actions.remove(category_key)
                return True

            if action_key in self._confirmed_actions or category_key in self._confirmed_actions:
                return True

        persistent = self._load_persistent_confirmations()
        if action_key in persistent or category_key in persistent:
            with self._lock:
                self._confirmed_actions.add(category_key)
            return True

        if self.file_level == "read_only" and action in ("write", "delete"):
            message = (
                f"File permission is read_only. Allow {action} on {path}?\n"
                f"Options: (y) yes, once  |  (a) yes, always this session  |  (p) yes, persist  |  (n) no"
            )
            answer = self._confirm(message)
            if not answer:
                return False

            # The callback is expected to return a string answer from the user.
            # If it returned a boolean True, treat as "once".
            if isinstance(answer, str):
                choice = answer.strip().lower()
                if choice in ("a", "always"):
                    with self._lock:
                        self._confirmed_actions.add(category_key)
                    return True
                if choice in ("p", "persist"):
                    with self._lock:
                        self._confirmed_actions.add(category_key)
                    self._save_persistent_confirmation(category_key)
                    return True
                if choice in ("n", "no", "negar"):
                    return False
            return True

        return False

    def ensure_write_allowed(self, path: Path) -> None:
        """Raise PermissionRequired if write is not explicitly allowed."""
        if self.can_write_file(path):
            return
        if self.confirm_action("write", path):
            return
        raise PermissionRequired(
            action="write",
            path=path,
            message=f"Write permission required for {path}",
        )

    def ensure_delete_allowed(self, path: Path) -> None:
        """Raise PermissionRequired if delete is not explicitly allowed."""
        if self.can_delete_file(path):
            return
        if self.confirm_action("delete", path):
            return
        raise PermissionRequired(
            action="delete",
            path=path,
            message=f"Delete permission required for {path}",
        )


# Dangerous shell command patterns (case-insensitive).
DANGEROUS_SHELL_PATTERNS = [
    re.compile(r"\brm\s+-rf\s+/"),
    re.compile(r"\bmkfs\."),
    re.compile(r"\bdd\s+if="),
    re.compile(r"\b:w!\s+"),
    re.compile(r"\bchmod\s+-R\s+777\s+/"),
    re.compile(r"\bcurl\s+.*\|\s*bash", re.IGNORECASE),
    re.compile(r"\bwget\s+.*\|\s*bash", re.IGNORECASE),
]

DANGEROUS_PYTHON_IMPORTS = {
    "builtins",
    "os",
    "subprocess",
    "sys",
    "ctypes",
    "socket",
    "urllib",
    "http",
    "ftplib",
    "telnetlib",
    "pickle",
    "marshal",
    "importlib",
}


def check_shell_safety(command: str) -> Optional[str]:
    """Return an error message if the command looks dangerous."""
    for pattern in DANGEROUS_SHELL_PATTERNS:
        if pattern.search(command):
            return f"Dangerous shell pattern blocked: {pattern.pattern}"
    return None


def check_python_safety(code: str, allow_install: bool = True) -> Optional[str]:
    """Return an error message if the Python code looks dangerous.

    Uses AST analysis to catch direct imports, dynamic imports, eval/exec,
    and attribute access on blocked modules (e.g. import os; os.system).
    """
    import ast

    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return f"Python syntax error: {e}"

    blocked_names = DANGEROUS_PYTHON_IMPORTS.copy()
    blocked_attrs = {
        "system", "popen", "spawn", "fork", "execv", "kill", "remove",
        "unlink", "rmdir", "rename", "replace", "open", "breakpoint",
    }
    dynamic_import_funcs = {"__import__", "import_module", "exec_module"}
    found_imports: Set[str] = set()
    found_dynamic: Set[str] = set()

    for node in ast.walk(tree):
        # Direct imports: import X or from X import ...
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in blocked_names:
                    found_imports.add(root)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                root = node.module.split(".")[0]
                if root in blocked_names:
                    found_imports.add(root)
        # Dynamic imports and dangerous builtins
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                if func.id in dynamic_import_funcs:
                    found_dynamic.add(func.id)
                if func.id in ("exec", "eval", "compile"):
                    found_dynamic.add(func.id)
                if func.id == "open":
                    found_dynamic.add("open")
            # Attribute calls like os.system, subprocess.Popen
            elif isinstance(func, ast.Attribute):
                if func.attr in blocked_attrs:
                    found_dynamic.add(f"{getattr(func.value, 'id', '?')}.{func.attr}")
        # Bare exec/eval/compile references
        elif isinstance(node, ast.Name):
            if node.id in ("exec", "eval", "compile"):
                found_dynamic.add(node.id)

    if found_imports:
        return f"Blocked Python imports: {', '.join(sorted(found_imports))}"
    if found_dynamic:
        return f"Blocked Python operations: {', '.join(sorted(found_dynamic))}"

    if not allow_install and re.search(r"\b(pip|conda)\b", code):
        return "Package installation is not allowed at this permission level."

    return None
