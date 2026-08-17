"""Permission manager for code and command execution.

ZEUS_EXECUTION_PERMISSION levels:
- "deny": no code/shell execution allowed
- "sandbox_only": only sandboxed execute_python/execute_shell_script allowed
- "allow": full access including run_terminal on host
"""

import os
import re
from typing import List, Optional


class PermissionManager:
    """Centralized execution permission controls."""

    LEVELS = ("deny", "sandbox_only", "allow")

    def __init__(self, level: Optional[str] = None):
        self.level = (level or os.getenv("ZEUS_EXECUTION_PERMISSION", "sandbox_only")).lower()
        if self.level not in self.LEVELS:
            self.level = "sandbox_only"

    def can_run_terminal(self) -> bool:
        return self.level == "allow"

    def can_run_sandboxed_shell(self) -> bool:
        return self.level in ("sandbox_only", "allow")

    def can_run_sandboxed_python(self) -> bool:
        return self.level in ("sandbox_only", "allow")

    def can_install_packages(self) -> bool:
        return self.level in ("sandbox_only", "allow")

    def denied_message(self, action: str) -> str:
        return (
            f"Execution denied: {action} is not allowed at permission level '{self.level}'. "
            f"Set ZEUS_EXECUTION_PERMISSION=allow to enable it."
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
}


def check_shell_safety(command: str) -> Optional[str]:
    """Return an error message if the command looks dangerous."""
    for pattern in DANGEROUS_SHELL_PATTERNS:
        if pattern.search(command):
            return f"Dangerous shell pattern blocked: {pattern.pattern}"
    return None


def check_python_safety(code: str, allow_install: bool = True) -> Optional[str]:
    """Return an error message if the Python code looks dangerous."""
    import_pattern = re.compile(r"^\s*import\s+(\S+)", re.MULTILINE)
    from_pattern = re.compile(r"^\s*from\s+(\S+)\s+import", re.MULTILINE)

    imports = set()
    for match in import_pattern.finditer(code):
        imports.add(match.group(1).split(".")[0])
    for match in from_pattern.finditer(code):
        imports.add(match.group(1).split(".")[0])

    blocked = imports & DANGEROUS_PYTHON_IMPORTS
    if blocked:
        return f"Blocked Python imports: {', '.join(sorted(blocked))}"

    if not allow_install and re.search(r"\b(pip|conda)\b", code):
        return "Package installation is not allowed at this permission level."

    return None
