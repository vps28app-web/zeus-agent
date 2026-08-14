"""Database query tool for Zeus to inspect its own SQLite store."""

from typing import Any, Dict, List, Optional

from zeus.core.registry import register_tool
from zeus.db.connection import get_connection


def query_database(query: str, params: Optional[List[Any]] = None, limit: int = 100) -> Dict[str, Any]:
    """Execute a read-only SQLite query against the Zeus database.

    Useful for inspecting memory, sessions, turns, and metrics.
    Only SELECT statements are allowed.
    """
    safe_query = query.strip()
    if not safe_query.lower().startswith("select"):
        return {"error": "Only SELECT queries are allowed."}

    if ";" in safe_query.rstrip(";"):
        return {"error": "Multiple statements are not allowed."}

    try:
        conn = get_connection()
        cursor = conn.execute(safe_query, params or [])
        rows = cursor.fetchmany(limit)
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        conn.close()
        return {
            "columns": columns,
            "rows": [dict(row) for row in rows],
            "row_count": len(rows),
        }
    except Exception as e:
        return {"error": str(e)}


register_tool(
    name="query_database",
    description="Query the Zeus SQLite database (read-only). Useful for inspecting memory, sessions, turns, and metrics. Only SELECT statements allowed.",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "SQL SELECT query."},
            "params": {"type": "array", "description": "Optional query parameters.", "default": []},
            "limit": {"type": "integer", "default": 100},
        },
        "required": ["query"],
    },
    handler=query_database,
)
