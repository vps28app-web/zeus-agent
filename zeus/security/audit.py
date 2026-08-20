"""Execution audit logging for security-sensitive operations."""

import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

from zeus.db.connection import init_db
from zeus.db.repository import AuditRepository


class AuditLogger:
    """Append-only audit log for code execution, shell commands and file mutations."""

    def __init__(self, log_dir: Optional[Path] = None):
        self._log_dir = (log_dir or Path(os.getenv("ZEUS_HOME", os.path.expanduser("~/.zeus"))) / "audit").expanduser().resolve()
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _log_path(self) -> Path:
        date = time.strftime("%Y-%m-%d")
        return self._log_dir / f"audit-{date}.jsonl"

    def log(
        self,
        action: str,
        details: Dict[str, Any],
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        allowed: bool = True,
    ) -> None:
        """Write a single audit entry to JSONL and SQLite."""
        entry = {
            "timestamp": time.time(),
            "action": action,
            "session_id": session_id or "anonymous",
            "user_id": user_id or "anonymous",
            "allowed": allowed,
            "details": details,
        }
        with self._lock:
            with self._log_path().open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, default=str) + "\n")

        try:
            init_db()
            repo = AuditRepository()
            repo.add(
                timestamp=entry["timestamp"],
                action=action,
                session_id=session_id,
                user_id=user_id,
                allowed=allowed,
                details=details,
            )
        except Exception:
            # SQLite persistence is best-effort; JSONL remains the source of truth.
            pass

    def log_execution(
        self,
        tool: str,
        command: str,
        result: Dict[str, Any],
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        allowed: bool = True,
    ) -> None:
        self.log(
            action=f"execution:{tool}",
            details={
                "command": command,
                "exit_code": result.get("exit_code"),
                "error": result.get("error"),
                "stdout_preview": str(result.get("stdout", ""))[:500],
            },
            session_id=session_id,
            user_id=user_id,
            allowed=allowed,
        )

    def log_file_mutation(
        self,
        action: str,
        path: Path,
        allowed: bool,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> None:
        self.log(
            action=f"file:{action}",
            details={"path": str(path)},
            session_id=session_id,
            user_id=user_id,
            allowed=allowed,
        )


# Singleton audit logger per process.
_AUDIT_LOGGER: Optional[AuditLogger] = None
_AUDIT_LOCK = threading.Lock()


def get_audit_logger() -> AuditLogger:
    global _AUDIT_LOGGER
    if _AUDIT_LOGGER is None:
        with _AUDIT_LOCK:
            if _AUDIT_LOGGER is None:
                _AUDIT_LOGGER = AuditLogger()
    return _AUDIT_LOGGER
