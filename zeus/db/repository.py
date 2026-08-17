"""Repository layer for Zeus SQLite database."""

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from zeus.db.connection import get_connection


class MemoryRepository:
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path

    def add(self, key: str, note: str) -> None:
        conn = get_connection(self.db_path)
        try:
            conn.execute(
                "INSERT INTO memories (key, note) VALUES (?, ?)",
                (key, note),
            )
            conn.commit()
        finally:
            conn.close()

    def get(self, key: str) -> List[str]:
        conn = get_connection(self.db_path)
        try:
            rows = conn.execute(
                "SELECT note FROM memories WHERE key = ? ORDER BY id",
                (key,),
            ).fetchall()
            return [row["note"] for row in rows]
        finally:
            conn.close()

    def keys(self) -> List[str]:
        conn = get_connection(self.db_path)
        try:
            rows = conn.execute(
                "SELECT DISTINCT key FROM memories ORDER BY key"
            ).fetchall()
            return [row["key"] for row in rows]
        finally:
            conn.close()

    def clear(self, key: Optional[str] = None) -> None:
        conn = get_connection(self.db_path)
        try:
            if key:
                conn.execute("DELETE FROM memories WHERE key = ?", (key,))
            else:
                conn.execute("DELETE FROM memories")
            conn.commit()
        finally:
            conn.close()

    def search(self, query: str) -> List[Dict[str, str]]:
        conn = get_connection(self.db_path)
        try:
            pattern = f"%{query}%"
            rows = conn.execute(
                "SELECT key, note FROM memories WHERE key LIKE ? OR note LIKE ? ORDER BY id",
                (pattern, pattern),
            ).fetchall()
            return [{"key": row["key"], "note": row["note"]} for row in rows]
        finally:
            conn.close()


class SessionRepository:
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path

    def ensure_session(self, session_id: str, platform: Optional[str] = None) -> None:
        conn = get_connection(self.db_path)
        try:
            conn.execute(
                "INSERT OR IGNORE INTO sessions (session_id, platform) VALUES (?, ?)",
                (session_id, platform),
            )
            conn.commit()
        finally:
            conn.close()

    def log_turn(
        self,
        session_id: str,
        role: str,
        content: Any,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.ensure_session(session_id)
        conn = get_connection(self.db_path)
        try:
            conn.execute(
                "INSERT INTO turns (session_id, role, content, metadata) VALUES (?, ?, ?, ?)",
                (
                    session_id,
                    role,
                    json.dumps(content, ensure_ascii=False) if not isinstance(content, str) else content,
                    json.dumps(metadata, ensure_ascii=False) if metadata else None,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def get_turns(self, session_id: str, limit: int = 1000) -> List[Dict[str, Any]]:
        conn = get_connection(self.db_path)
        try:
            rows = conn.execute(
                "SELECT role, content, metadata, created_at FROM turns WHERE session_id = ? ORDER BY id LIMIT ?",
                (session_id, limit),
            ).fetchall()
            return [
                {
                    "role": row["role"],
                    "content": row["content"],
                    "metadata": json.loads(row["metadata"]) if row["metadata"] else None,
                    "created_at": row["created_at"],
                }
                for row in rows
            ]
        finally:
            conn.close()

    def list_sessions(self) -> List[str]:
        conn = get_connection(self.db_path)
        try:
            rows = conn.execute(
                "SELECT session_id FROM sessions ORDER BY created_at DESC"
            ).fetchall()
            return [row["session_id"] for row in rows]
        finally:
            conn.close()


class MetricsRepository:
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path

    def record_tool_call(
        self,
        session_id: str,
        tool_name: str,
        latency_ms: float,
        error: bool,
        result_summary: Optional[str] = None,
    ) -> None:
        conn = get_connection(self.db_path)
        try:
            conn.execute(
                "INSERT INTO metrics (session_id, tool_name, latency_ms, error, result_summary) VALUES (?, ?, ?, ?, ?)",
                (session_id, tool_name, latency_ms, int(error), result_summary),
            )
            conn.commit()
        finally:
            conn.close()

    def record_llm_call(
        self,
        session_id: str,
        input_tokens: int,
        output_tokens: int,
    ) -> None:
        conn = get_connection(self.db_path)
        try:
            conn.execute(
                "INSERT INTO metrics (session_id, llm_input_tokens, llm_output_tokens) VALUES (?, ?, ?)",
                (session_id, input_tokens, output_tokens),
            )
            conn.commit()
        finally:
            conn.close()

    def session_summary(self, session_id: str) -> Dict[str, Any]:
        conn = get_connection(self.db_path)
        try:
            tool_stats = conn.execute(
                """
                SELECT tool_name, COUNT(*) as calls, SUM(error) as errors, AVG(latency_ms) as avg_latency
                FROM metrics
                WHERE session_id = ? AND tool_name IS NOT NULL
                GROUP BY tool_name
                """,
                (session_id,),
            ).fetchall()

            token_stats = conn.execute(
                """
                SELECT COALESCE(SUM(llm_input_tokens), 0) as input_tokens,
                       COALESCE(SUM(llm_output_tokens), 0) as output_tokens,
                       COUNT(*) as llm_calls
                FROM metrics
                WHERE session_id = ? AND llm_input_tokens IS NOT NULL
                """,
                (session_id,),
            ).fetchone()

            return {
                "session_id": session_id,
                "tool_calls": [
                    {
                        "tool": row["tool_name"],
                        "calls": row["calls"],
                        "errors": row["errors"],
                        "avg_latency_ms": round(row["avg_latency"], 2) if row["avg_latency"] else 0,
                    }
                    for row in tool_stats
                ],
                "llm_calls": token_stats["llm_calls"],
                "llm_input_tokens": token_stats["input_tokens"],
                "llm_output_tokens": token_stats["output_tokens"],
            }
        finally:
            conn.close()


class ScheduledTaskRepository:
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path

    def create(
        self,
        task_id: str,
        session_id: str,
        command: str,
        schedule: str,
        description: Optional[str] = None,
        next_run: Optional[str] = None,
    ) -> None:
        conn = get_connection(self.db_path)
        try:
            conn.execute(
                """INSERT INTO scheduled_tasks
                (task_id, session_id, command, schedule, description, next_run)
                VALUES (?, ?, ?, ?, ?, ?)""",
                (task_id, session_id, command, schedule, description, next_run),
            )
            conn.commit()
        finally:
            conn.close()

    def get(self, task_id: str) -> Optional[Dict[str, Any]]:
        conn = get_connection(self.db_path)
        try:
            row = conn.execute(
                "SELECT * FROM scheduled_tasks WHERE task_id = ?", (task_id,)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def list_all(self) -> List[Dict[str, Any]]:
        conn = get_connection(self.db_path)
        try:
            rows = conn.execute(
                "SELECT * FROM scheduled_tasks ORDER BY next_run"
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def list_due(self) -> List[Dict[str, Any]]:
        conn = get_connection(self.db_path)
        try:
            rows = conn.execute(
                """SELECT * FROM scheduled_tasks
                WHERE enabled = 1 AND next_run <= datetime('now')
                ORDER BY next_run""",
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def update_next_run(self, task_id: str, next_run: str) -> None:
        conn = get_connection(self.db_path)
        try:
            conn.execute(
                "UPDATE scheduled_tasks SET next_run = ? WHERE task_id = ?",
                (next_run, task_id),
            )
            conn.commit()
        finally:
            conn.close()

    def set_enabled(self, task_id: str, enabled: bool) -> None:
        conn = get_connection(self.db_path)
        try:
            conn.execute(
                "UPDATE scheduled_tasks SET enabled = ? WHERE task_id = ?",
                (int(enabled), task_id),
            )
            conn.commit()
        finally:
            conn.close()

    def delete(self, task_id: str) -> None:
        conn = get_connection(self.db_path)
        try:
            conn.execute("DELETE FROM scheduled_tasks WHERE task_id = ?", (task_id,))
            conn.commit()
        finally:
            conn.close()


class UserProfileRepository:
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path

    def _parse(self, row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "user_id": row["user_id"],
            "platform": row["platform"],
            "name": row["name"],
            "preferences": json.loads(row["preferences"]) if row["preferences"] else [],
            "habits": json.loads(row["habits"]) if row["habits"] else [],
            "raw_notes": row["raw_notes"] or "",
            "updated_at": row["updated_at"],
            "created_at": row["created_at"],
        }

    def upsert(
        self,
        user_id: str,
        platform: Optional[str] = None,
        name: Optional[str] = None,
        preferences: Optional[List[str]] = None,
        habits: Optional[List[str]] = None,
        raw_notes: Optional[str] = None,
    ) -> None:
        conn = get_connection(self.db_path)
        try:
            existing = conn.execute(
                "SELECT * FROM user_profiles WHERE user_id = ?", (user_id,)
            ).fetchone()

            if existing:
                merged_name = name if name is not None else existing["name"]
                merged_preferences = self._merge_json_list(
                    existing["preferences"], preferences
                )
                merged_habits = self._merge_json_list(existing["habits"], habits)
                merged_notes = self._merge_text(existing["raw_notes"], raw_notes)
                conn.execute(
                    """UPDATE user_profiles SET
                        platform = COALESCE(?, platform),
                        name = ?,
                        preferences = ?,
                        habits = ?,
                        raw_notes = ?,
                        updated_at = datetime('now')
                    WHERE user_id = ?""",
                    (
                        platform,
                        merged_name,
                        json.dumps(merged_preferences, ensure_ascii=False),
                        json.dumps(merged_habits, ensure_ascii=False),
                        merged_notes,
                        user_id,
                    ),
                )
            else:
                conn.execute(
                    """INSERT INTO user_profiles
                        (user_id, platform, name, preferences, habits, raw_notes)
                    VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        user_id,
                        platform,
                        name,
                        json.dumps(preferences or [], ensure_ascii=False),
                        json.dumps(habits or [], ensure_ascii=False),
                        raw_notes or "",
                    ),
                )
            conn.commit()
        finally:
            conn.close()

    def _merge_json_list(self, existing_json: Optional[str], new_items: Optional[List[str]]) -> List[str]:
        existing: List[str] = []
        if existing_json:
            try:
                existing = json.loads(existing_json)
            except Exception:
                pass
        if not new_items:
            return existing
        combined = existing + [i for i in new_items if i not in existing]
        return combined

    def _merge_text(self, existing: Optional[str], new_text: Optional[str]) -> str:
        existing = existing or ""
        new_text = new_text or ""
        if not new_text.strip():
            return existing
        if existing.strip() in new_text.strip() or new_text.strip() in existing.strip():
            return existing if len(existing) >= len(new_text) else new_text
        return f"{existing}\n{new_text}".strip()

    def get(self, user_id: str) -> Optional[Dict[str, Any]]:
        conn = get_connection(self.db_path)
        try:
            row = conn.execute(
                "SELECT * FROM user_profiles WHERE user_id = ?", (user_id,)
            ).fetchone()
            return self._parse(row) if row else None
        finally:
            conn.close()

    def list_all(self) -> List[Dict[str, Any]]:
        conn = get_connection(self.db_path)
        try:
            rows = conn.execute(
                "SELECT * FROM user_profiles ORDER BY updated_at DESC"
            ).fetchall()
            return [self._parse(row) for row in rows]
        finally:
            conn.close()

    def delete(self, user_id: str) -> None:
        conn = get_connection(self.db_path)
        try:
            conn.execute("DELETE FROM user_profiles WHERE user_id = ?", (user_id,))
            conn.commit()
        finally:
            conn.close()
