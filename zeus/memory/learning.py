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
        """Heuristic extraction of a learning from a session's turn history.

        Looks for sequences where one or more tool calls errored and a later
        response succeeded, then stores the resolution pattern.
        """
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
                if isinstance(content, str):
                    final_response = content

        if not user_input or not final_response:
            return None

        # Only store if there was at least one error and a later success.
        if not tool_errors:
            return None

        problem = f"Task: {user_input[:200]}"
        solution = f"Resolved by: {final_response[:400]}"
        failure_pattern = "; ".join(tool_errors[:3])
        tags = list({"resolution", "auto-learned"} | set(tools_used))

        learning_id = self.save(
            problem=problem,
            solution=solution,
            session_id=session_id,
            tools_used=list(set(tools_used)),
            tags=tags,
            effectiveness_score=1,
            failure_pattern=failure_pattern,
        )
        return self._repo.get(learning_id)
