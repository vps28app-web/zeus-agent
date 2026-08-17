"""Persistent reasoning memory: save useful chains of thought per user/task."""

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from zeus.db.connection import init_db
from zeus.db.repository import MemoryRepository


class ReasoningMemory:
    """Store and retrieve useful reasoning patterns and replanning insights per user."""

    def __init__(self, user_id: Optional[str] = None, repo: Optional[MemoryRepository] = None):
        init_db()
        self._repo = repo or MemoryRepository()
        self.user_id = user_id or "anonymous"

    def _key(self) -> str:
        return f"reasoning_memory:{self.user_id}"

    def _load(self) -> List[Dict[str, Any]]:
        notes = self._repo.get(self._key())
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
            "user_id": self.user_id,
        }
        # Avoid exact duplicates.
        existing = self._load()
        for e in existing:
            if e.get("task") == task and e.get("reasoning") == reasoning:
                return
        self._repo.add(self._key(), json.dumps(entry, ensure_ascii=False))

    def _semantic_score(self, query: str, entry: Dict[str, Any]) -> float:
        """Simple keyword-based relevance score (fallback when embeddings unavailable)."""
        query_words = set(query.lower().split())
        text = f"{entry.get('task', '')} {entry.get('reasoning', '')} {entry.get('outcome', '')} {' '.join(entry.get('tags', []))}"
        text_words = set(text.lower().split())
        if not query_words:
            return 0.0
        overlap = query_words & text_words
        return len(overlap) / len(query_words)

    def _embed_text(self, text: str) -> Optional[List[float]]:
        """Try to get embeddings from Ollama if available."""
        import requests

        model = os.getenv("ZEUS_EMBEDDING_MODEL", "nomic-embed-text")
        host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
        try:
            resp = requests.post(
                f"{host}/api/embeddings",
                json={"model": model, "prompt": text},
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json().get("embedding")
        except Exception:
            return None

    def _cosine_similarity(self, a: List[float], b: List[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(x * x for x in b) ** 0.5
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    def recall(self, query: str, limit: int = 3) -> List[Dict[str, Any]]:
        """Search reasoning memory for entries matching a query."""
        all_entries = self._load()
        if not all_entries:
            return []

        query_embedding = self._embed_text(query)
        if query_embedding:
            scored = []
            for entry in all_entries:
                text = f"{entry.get('task', '')} {entry.get('reasoning', '')}"
                emb = self._embed_text(text)
                if emb:
                    score = self._cosine_similarity(query_embedding, emb)
                else:
                    score = self._semantic_score(query, entry)
                scored.append((score, entry))
            scored.sort(key=lambda x: x[0], reverse=True)
            return [e for _, e in scored[:limit]]

        # Fallback to keyword scoring.
        scored = [(self._semantic_score(query, entry), entry) for entry in all_entries]
        scored.sort(key=lambda x: x[0], reverse=True)
        return [e for _, e in scored[:limit] if _ > 0]

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
        self._repo.clear(self._key())
