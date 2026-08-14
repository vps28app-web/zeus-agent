"""Simple JSON-backed memory store with optional SQLite backend."""

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from zeus.db.repository import MemoryRepository


def _memory_path() -> Path:
    home = os.getenv("ZEUS_HOME", os.path.expanduser("~/.zeus"))
    path = Path(home)
    path.mkdir(parents=True, exist_ok=True)
    return path / "memory.json"


class MemoryStore:
    def __init__(self, path: Optional[Path] = None):
        self.json_path = path or _memory_path()
        self.use_sqlite = os.getenv("ZEUS_USE_SQLITE", "true").lower() in ("1", "true", "yes")
        if self.use_sqlite:
            from zeus.db.connection import init_db
            init_db()
            self._repo: Optional[MemoryRepository] = MemoryRepository()
        else:
            self._repo = None
            self._data: Dict[str, List[str]] = self._load()

    def _load(self) -> Dict[str, List[str]]:
        if not self.json_path.exists():
            return {}
        try:
            with self.json_path.open("r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save(self) -> None:
        self.json_path.parent.mkdir(parents=True, exist_ok=True)
        with self.json_path.open("w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)

    def append(self, key: str, note: str) -> None:
        if self.use_sqlite and self._repo:
            self._repo.add(key, note)
        else:
            self._data.setdefault(key, []).append(note)
            self._save()

    def get(self, key: str) -> List[str]:
        if self.use_sqlite and self._repo:
            return self._repo.get(key)
        return self._data.get(key, [])

    def keys(self) -> List[str]:
        if self.use_sqlite and self._repo:
            return self._repo.keys()
        return list(self._data.keys())

    def clear(self, key: Optional[str] = None) -> None:
        if self.use_sqlite and self._repo:
            self._repo.clear(key)
        else:
            if key:
                self._data.pop(key, None)
            else:
                self._data = {}
            self._save()
