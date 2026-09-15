"""Permission manager for code, command, and file-system operations.

ZEUS_EXECUTION_PERMISSION levels:
- "deny": no code/shell execution allowed
- "sandbox_only": only sandboxed execute_python/execute_shell_script allowed
- "allow": full access including run_terminal on host

ZEUS_FILE_PERMISSION levels:
- "read_only": only read/list files; writes/deletes require user confirmation
- "project_only": read/write allowed only inside project dir without confirmation
- "unrestricted": full access without confirmation

ZEUS_EXECUTION_MODE controls runtime behavior around terminal execution:
- "terminal": ask user confirmation for medium/high-risk terminal commands
- "auto": execute terminal commands automatically, only show the result

ZEUS_DRY_RUN when "1" makes every mutating tool return a simulation instead
of actually executing.

Confirmed actions are persisted per session in memory and optionally per user in SQLite.
"""

import json
import os
import re
import threading
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Set


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
    EXECUTION_MODES = ("terminal", "auto")

    # Tools that are never allowed when read-only mode is active.
    READ_ONLY_BLOCKED_TOOLS = {
        "write_file",
        "replace_file_content",
        "move_file",
        "copy_file",
        "delete_file",
        "run_terminal",
        "run_background_command",
        "terminate_command",
        "execute_python",
        "execute_shell_script",
        "manage_packages",
        "git_commit",
        "git_push",
        "git_reset",
        "git_clean",
        "git_checkout",
        "scheduler_schedule",
    }

    # Tools that always require confirmation in terminal mode (human-in-the-loop).
    TERMINAL_CONFIRM_TOOLS = {
        "run_terminal",
        "run_background_command",
        "terminate_command",
        "manage_packages",
        "git_push",
        "git_reset",
        "git_clean",
        "git_checkout",
    }

    def __init__(
        self,
        exec_level: Optional[str] = None,
        file_level: Optional[str] = None,
        project_dir: Optional[Path] = None,
        confirm_callback: Optional[Callable[[str], bool]] = None,
        user_id: Optional[str] = None,
    ):
        self._exec_level_override = exec_level.lower() if exec_level else None
        self._file_level_override = file_level.lower() if file_level else None

        self.project_dir = (project_dir or Path(os.getenv("ZEUS_PROJECT_DIR", Path.cwd()))).resolve()
        self.confirm_callback = confirm_callback
        self.user_id = user_id or "anonymous"

        # In-memory session confirmations.
        self._confirmed_actions: Set[str] = set()
        self._once_confirmed_actions: Set[str] = set()
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Env-backed properties
    # ------------------------------------------------------------------
    @property
    def exec_level(self) -> str:
        level = self._exec_level_override or os.getenv("ZEUS_EXECUTION_PERMISSION", "sandbox_only")
        level = level.lower()
        return level if level in self.EXEC_LEVELS else "sandbox_only"

    @exec_level.setter
    def exec_level(self, value: str) -> None:
        self._exec_level_override = value.lower() if value else None

    @property
    def file_level(self) -> str:
        level = self._file_level_override or os.getenv("ZEUS_FILE_PERMISSION", "read_only")
        level = level.lower()
        return level if level in self.FILE_LEVELS else "read_only"

    @file_level.setter
    def file_level(self, value: str) -> None:
        self._file_level_override = value.lower() if value else None

    @property
    def execution_mode(self) -> str:
        mode = os.getenv("ZEUS_EXECUTION_MODE", "terminal").lower()
        return mode if mode in self.EXECUTION_MODES else "terminal"

    @property
    def dry_run(self) -> bool:
        return os.getenv("ZEUS_DRY_RUN", "0").strip().lower() in ("1", "true", "yes", "on")

    @property
    def read_only(self) -> bool:
        return os.getenv("ZEUS_READ_ONLY", "0").strip().lower() in ("1", "true", "yes", "on")

    # ------------------------------------------------------------------
    # Mode helpers
    # ------------------------------------------------------------------
    def is_tool_allowed(self, tool_name: str) -> bool:
        """Return False if the tool is blocked by read-only mode."""
        if not self.read_only:
            return True
        return tool_name not in self.READ_ONLY_BLOCKED_TOOLS

    def is_confirmation_required(self, tool_name: str, arguments: Optional[Dict[str, Any]] = None) -> bool:
        """Return True if the tool should prompt for explicit user confirmation."""
        if self.execution_mode == "auto":
            return False
        if tool_name not in self.TERMINAL_CONFIRM_TOOLS:
            return False
        # For terminal commands, high/medium risk always asks in terminal mode.
        risk = self.classify_tool_risk(tool_name, arguments or {})
        return risk in ("high", "medium")

    def classify_tool_risk(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Classify the risk level of a tool call (none, medium, high)."""
        if tool_name in ("run_terminal", "run_background_command"):
            command = (arguments.get("command") or "").lower()
            stripped = command.strip()
            if not stripped:
                return "none"

            # High-risk shell patterns.
            dangerous = [
                r"\brm\s+-rf\s+/",
                r"\bmkfs\.",
                r"\bdd\s+if=",
                r"\bchmod\s+-R\s+777\s+/",
                r"\bcurl\s+.*\|\s*bash",
                r"\bwget\s+.*\|\s*bash",
                r"\bsudo\b",
                r"\bshutdown\b",
                r"\breboot\b",
                r"\bformat\b",
                r"\bfdisk\b",
                r"\bdocker\s+(system\s+prune|rm\s+-f)",
                r">\s*/dev/[sh]d",
                r"\bkill\s+-9\b",
            ]
            for pattern in dangerous:
                if re.search(pattern, command, re.IGNORECASE):
                    return "high"

            # Medium-risk if it mutates system/project state.
            medium = [
                r"\b(apt|apt-get|yum|dnf|pacman|brew)\s+(install|remove|purge|autoremove|upgrade|update)",
                r"\bpip\s+(install|uninstall)",
                r"\brm\s+-rf\b",
                r"\bgit\s+push\b",
                r"\bgit\s+reset\s+--hard\b",
                r"\bgit\s+clean\b",
                r"\bsystemctl\b",
                r"\bservice\s+\w+\s+(start|stop|restart)",
            ]
            for pattern in medium:
                if re.search(pattern, command, re.IGNORECASE):
                    return "medium"

            return "medium"

        if tool_name == "terminate_command":
            return "low"

        if tool_name == "manage_packages":
            operation = (arguments.get("operation") or "").lower()
            if operation in ("install", "remove", "purge", "update", "upgrade"):
                return "high" if operation in ("remove", "purge") else "medium"
            return "low"

        if tool_name in ("git_push", "git_reset", "git_clean", "git_checkout"):
            return "high" if tool_name == "git_reset" else "medium"

        return "none"

    def confirm_tool(self, tool_name: str, arguments: Dict[str, Any], scope: str = "once") -> bool:
        """Ask the user for permission to execute a risky tool."""
        action_key = f"tool:{tool_name}:{self._tool_signature(tool_name, arguments)}"
        category_key = f"tool:{tool_name}:*"

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

        summary = self._format_tool_summary(tool_name, arguments)
        message = (
            f"Execution confirmation / Confirmação de execução:\n"
            f"  • Tool / Ferramenta: {tool_name}\n"
            f"  • Command / Comando: {summary}\n"
            f"  • Mode / Modo: {self.execution_mode}"
        )
        answer = self._confirm(message)
        choice = self._normalize_confirmation_answer(answer)
        if choice == "deny" or choice is None:
            return False
        if choice == "always":
            with self._lock:
                self._confirmed_actions.add(category_key)
            return True
        if choice == "persist":
            with self._lock:
                self._confirmed_actions.add(category_key)
            self._save_persistent_confirmation(category_key)
            return True
        with self._lock:
            self._once_confirmed_actions.add(action_key)
        return True

    def _tool_signature(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Create a stable signature for a specific tool call."""
        if tool_name in ("run_terminal", "run_background_command"):
            return arguments.get("command", "")
        if tool_name == "manage_packages":
            return f"{arguments.get('operation')}:{arguments.get('package_name')}"
        if tool_name.startswith("git_"):
            return arguments.get("args", "")
        return json.dumps(arguments, sort_keys=True, default=str)

    def _format_tool_summary(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Human-readable summary of a tool call for confirmation prompts."""
        if tool_name in ("run_terminal", "run_background_command"):
            return arguments.get("command", "")
        if tool_name == "terminate_command":
            return f"command_id={arguments.get('command_id', '')}"
        if tool_name == "manage_packages":
            return f"{arguments.get('operation')} {arguments.get('package_name', '')}"
        if tool_name.startswith("git_"):
            return arguments.get("args", "")
        return json.dumps(arguments, sort_keys=True, default=str)

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
            f"Execution denied / Execução negada: {action} is not allowed at permission level / "
            f"não é permitido no nível '{self.exec_level}'. "
            f"Switch to host mode / Mude para modo host: /mode terminal "
            f"(or / ou ZEUS_EXECUTION_PERMISSION=allow)."
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

    def _normalize_confirmation_answer(self, answer) -> Optional[str]:
        """Normalize callback answer into one of 'once', 'always', 'persist', 'deny' or None."""
        if answer is True:
            return "once"
        if answer is False:
            return "deny"
        if not isinstance(answer, str):
            return None
        choice = answer.strip().lower()
        if choice in ("y", "yes", "sim", "once"):
            return "once"
        if choice in ("a", "always", "sempre"):
            return "always"
        if choice in ("p", "persist", "persistir"):
            return "persist"
        if choice in ("n", "no", "nao", "não", "negar", "deny"):
            return "deny"
        return None

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

        action_label = "Write / Escrita ✍️" if action == "write" else "Delete / Exclusão 🗑️"
        message = (
            f"File permission request / Solicitação de permissão de arquivo:\n"
            f"  • Operation / Operação: {action_label}\n"
            f"  • File / Arquivo: {path}\n"
            f"  • Permission level / Nível de permissão atual: {self.file_level}"
        )
        answer = self._confirm(message)

        choice = self._normalize_confirmation_answer(answer)
        if choice == "deny" or choice is None:
            return False
        if choice == "always":
            with self._lock:
                self._confirmed_actions.add(category_key)
            return True
        if choice == "persist":
            with self._lock:
                self._confirmed_actions.add(category_key)
            self._save_persistent_confirmation(category_key)
            return True
        # "once" or legacy truthy answer
        with self._lock:
            self._once_confirmed_actions.add(action_key)
        return True


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
    # Pipe to interpreter with optional whitespace
    re.compile(r"\bcurl\b.*\|\s*(?:bash|sh|zsh|perl|python|ruby)", re.IGNORECASE),
    re.compile(r"\bwget\b.*\|\s*(?:bash|sh|zsh|perl|python|ruby)", re.IGNORECASE),
    re.compile(r"\bfetch\b.*\|\s*(?:bash|sh|zsh|perl|python|ruby)", re.IGNORECASE),
    # Backticks and $() executing remote downloads
    re.compile(r"`.*(?:curl|wget|fetch)\b.*`", re.IGNORECASE),
    re.compile(r"\$\(.*(?:curl|wget|fetch)\b.*\)", re.IGNORECASE),
    # Obfuscated pipes
    re.compile(r"\b(?:curl|wget|fetch)\b.*\|\s*\$\(which\s+(?:bash|sh|zsh)\)", re.IGNORECASE),
    re.compile(r"\b(?:curl|wget|fetch)\b.*;\s*\brm\s+-rf\s+/", re.IGNORECASE),
]

# Global PermissionManager instance used by tools that do not inject their own.
_global_permission_manager: Optional[PermissionManager] = None


def set_global_permission_manager(pm: PermissionManager) -> None:
    """Set the global PermissionManager used by tools and the agent executor."""
    global _global_permission_manager
    _global_permission_manager = pm


def get_global_permission_manager() -> PermissionManager:
    """Return the configured global PermissionManager, creating a default if needed."""
    global _global_permission_manager
    if _global_permission_manager is None:
        _global_permission_manager = PermissionManager()
    return _global_permission_manager


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
