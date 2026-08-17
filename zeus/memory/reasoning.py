"""Persistent reasoning memory: save useful chains of thought per user/task."""

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from zeus.db.connection import init_db
from zeus.db.repository import MemoryRepository


class ReasoningMemory:
    """Store and retrieve useful reasoning patterns and replanning insights."""

    REASONING_KEY = "reasoning_memory"

    def __init__(self, repo: Optional[MemoryRepository] = None):
        init_db()
        self._repo = repo or MemoryRepository()

    def _load(self) -> List[Dict[str, Any]]:
        notes = self._repo.get(self.REASONING_KEY)
        parsed = []
        for note in notes:
            try:
                parsed.append(json.loads(note))
            except Exception:
                pass
        return parsed

    def save(
        self,
        task: str,
        reasoning: str,
        outcome: str,
        tags: Optional[List[str]] = None,
    ) -> None:
        """Save a useful reasoning chain if it produced a successful outcome."""
        entry = {
            "task": task,
            "reasoning": reasoning,
            "outcome": outcome,
            "tags": tags or [],
        }
        # Avoid exact duplicates.
        existing = self._load()
        for e in existing:
            if e.get("task") == task and e.get("reasoning") == reasoning:
                return
        self._repo.add(self.REASONING_KEY, json.dumps(entry, ensure_ascii=False))

    def recall(self, query: str, limit: int = 3) -> List[Dict[str, Any]]:
        """Search reasoning memory for entries matching a query."""
        results = self._repo.search(query)
        matches = []
        for r in results:
            if r["key"] != self.REASONING_KEY:
                continue
            try:
                matches.append(json.loads(r["note"]))
            except Exception:
                continue
            if len(matches) >= limit:
                break
        return matches

    def format_context(self, task: str) -> str:
        """Return relevant past reasoning as context string."""
        entries = self.recall(task, limit=2)
        if not entries:
            return ""
        lines = ["## Past Reasoning Insights"]
        for e in entries:
            lines.append(f"- Task: {e.get('task')}")
            lines.append(f"  Reasoning: {e.get('reasoning')}")
            lines.append(f"  Outcome: {e.get('outcome')}")
        return "\n".join(lines)

    def clear(self) -> None:
        self._repo.clear(self.REASONING_KEY)
