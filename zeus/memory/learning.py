"""Continuous learning: capture, search, and apply resolutions from past problem solving."""

import json
from typing import Any, Dict, List, Optional

from zeus.db.connection import init_db
from zeus.db.repository import LearningRepository


class LearningStore:
    """Store and retrieve problem/solution patterns learned from agent runs."""

    def __init__(self, user_id: Optional[str] = None, repo: Optional[LearningRepository] = None):
        if repo is None:
            init_db()
        self._repo = repo or LearningRepository()
        self.user_id = user_id

    def save(
        self,
        problem: str,
        solution: str,
        session_id: Optional[str] = None,
        tools_used: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        effectiveness_score: int = 0,
        failure_pattern: Optional[str] = None,
    ) -> int:
        """Persist a learned problem/solution pattern."""
        if not problem.strip() or not solution.strip():
            return 0
        # Avoid exact duplicate problem/solution pairs.
        existing = self._repo.search(query=problem[:120], user_id=self.user_id, limit=20)
        for entry in existing:
            if entry["problem"] == problem and entry["solution"] == solution:
                self._repo.update_score(entry["id"], 1)
                return entry["id"]
        return self._repo.add(
            problem=problem,
            solution=solution,
            user_id=self.user_id,
            session_id=session_id,
            tools_used=tools_used,
            tags=tags,
            effectiveness_score=effectiveness_score,
            failure_pattern=failure_pattern,
        )

    def search(
        self,
        query: str,
        tags: Optional[List[str]] = None,
        limit: int = 3,
    ) -> List[Dict[str, Any]]:
        """Search learnings relevant to a query, optionally filtered by tags."""
        return self._repo.search(query=query, tags=tags, user_id=self.user_id, limit=limit)

    def list_recent(self, limit: int = 10) -> List[Dict[str, Any]]:
        return self._repo.list_recent(limit=limit)

    def rate(self, learning_id: int, helpful: bool) -> bool:
        """Increase or decrease the effectiveness score of a learning."""
        delta = 1 if helpful else -1
        self._repo.update_score(learning_id, delta)
        return True

    def delete(self, learning_id: int) -> bool:
        """Delete a specific learning entry."""
        self._repo.delete(learning_id)
        return True

    def get_stats(self) -> Dict[str, Any]:
        """Get summary metrics of current learnings stored."""
        recent = self._repo.list_recent(limit=500)
        total = len(recent)
        positive_count = sum(1 for e in recent if e.get("effectiveness_score", 0) > 0)
        auto_learned = sum(1 for e in recent if "auto-learned" in e.get("tags", []))
        all_tags: Dict[str, int] = {}
        for e in recent:
            for tag in e.get("tags", []):
                all_tags[tag] = all_tags.get(tag, 0) + 1
        return {
            "total_learnings": total,
            "high_effectiveness": positive_count,
            "auto_learned": auto_learned,
            "tags_summary": all_tags,
        }

    def process_user_feedback(self, text: str, session_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Detect praise or dissatisfaction in user text and update recent learnings score."""
        lowered = text.lower().strip()
        negative_signals = [
            "não funcionou", "nao funcionou", "errado", "ficou ruim", "incorreto",
            "pessimo", "péssimo", "não deu certo", "nao deu certo", "está errado", "ruim"
        ]
        positive_signals = [
            "ótimo", "otimo", "perfeito", "excelente", "muito bom", "deu certo",
            "funciona", "funcionou", "parabéns", "parabens", "brilhante", "gostei", "correto"
        ]

        is_neg = any(sig in lowered for sig in negative_signals)
        is_pos = not is_neg and any(sig in lowered for sig in positive_signals)

        if not is_pos and not is_neg:
            return None

        recent = self._repo.list_recent(limit=5)
        if not recent:
            return None

        delta = 1 if is_pos else -1
        updated_ids = []
        for entry in recent[:3]:
            self._repo.update_score(entry["id"], delta)
            updated_ids.append(entry["id"])

        return {
            "feedback_type": "positive" if is_pos else "negative",
            "delta": delta,
            "updated_learnings": updated_ids,
        }

    def format_context(self, task: str, tags: Optional[List[str]] = None) -> str:
        """Return relevant learnings as a context string for the system prompt."""
        entries = self.search(task, tags=tags, limit=3)
        if not entries:
            return ""
        lines = ["## Learnings from Past Problem Solving"]
        for e in entries:
            lines.append(f"- Problem: {e['problem']}")
            lines.append(f"  Solution: {e['solution']}")
            if e.get("tools_used"):
                lines.append(f"  Tools: {', '.join(e['tools_used'])}")
            if e.get("failure_pattern"):
                lines.append(f"  Failure pattern: {e['failure_pattern']}")
        return "\n".join(lines)

    def extract_from_session(
        self,
        session_id: str,
        turns: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        """Extraction of learning patterns from a session turn history."""
        if len(turns) < 3:
            return None

        user_input = ""
        tool_errors: List[str] = []
        tools_used: List[str] = []
        final_response = ""

        for turn in turns:
            role = turn.get("role")
            content = turn.get("content", "")
            if role == "user":
                if not user_input:
                    user_input = content if isinstance(content, str) else str(content)
            elif role == "tool":
                try:
                    data = json.loads(content) if isinstance(content, str) else content
                except Exception:
                    data = {}
                tool_name = data.get("tool") or turn.get("name", "unknown")
                tools_used.append(tool_name)
                if data.get("error"):
                    tool_errors.append(f"{tool_name}: {data['error']}")
            elif role == "assistant":
                if isinstance(content, str) and content.strip():
                    final_response = content.strip()

        if not user_input or not final_response:
            return None

        # Capture pattern if tool errors occurred OR if multi-tool interaction succeeded
        problem = f"Task: {user_input[:200]}"
        solution = f"Resolved by: {final_response[:400]}"
        failure_pattern = "; ".join(tool_errors[:3]) if tool_errors else None
        score = 2 if tool_errors else 1
        tags = list({"resolution", "auto-learned"} | set(tools_used))

        learning_id = self.save(
            problem=problem,
            solution=solution,
            session_id=session_id,
            tools_used=list(set(tools_used)),
            tags=tags,
            effectiveness_score=score,
            failure_pattern=failure_pattern,
        )
        return self._repo.get(learning_id)
