"""Session logging: persist conversation turns to disk and SQLite."""

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from zeus.db.repository import SessionRepository


def _logs_path() -> Path:
    home = os.getenv("ZEUS_HOME", os.path.expanduser("~/.zeus"))
    path = Path(home) / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


class SessionLogger:
    def __init__(self, session_id: Optional[str] = None):
        self.session_id = session_id or uuid.uuid4().hex[:12]
        self.log_path = _logs_path() / f"{self.session_id}.jsonl"
        self.turns: List[Dict[str, Any]] = []
        self.use_sqlite = os.getenv("ZEUS_USE_SQLITE", "true").lower() in ("1", "true", "yes")
        if self.use_sqlite:
            from zeus.db.connection import init_db
            init_db()
            self._repo: Optional[SessionRepository] = SessionRepository()
            self._repo.ensure_session(self.session_id)
        else:
            self._repo = None

    def log_turn(self, role: str, content: Any, metadata: Optional[Dict[str, Any]] = None) -> None:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "session_id": self.session_id,
            "role": role,
            "content": content,
        }
        if metadata:
            entry["metadata"] = metadata
        self.turns.append(entry)
        self._append(entry)
        if self.use_sqlite and self._repo:
            self._repo.log_turn(self.session_id, role, content, metadata)

    def _append(self, entry: Dict[str, Any]) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def list_sessions(self) -> List[str]:
        if self.use_sqlite and self._repo:
            return self._repo.list_sessions()
        return sorted(p.stem for p in _logs_path().glob("*.jsonl"))


def get_logger(session_id: Optional[str] = None) -> SessionLogger:
    return SessionLogger(session_id)
