"""Database query tool for Zeus to inspect its own SQLite store."""

from typing import Any, Dict, List, Optional

from zeus.core.registry import register_tool
from zeus.db.connection import get_connection

# Tables that query_database is allowed to read.
ALLOWED_TABLES = {
    "memories", "sessions", "turns", "metrics",
    "user_profiles", "learnings",
}

# Tables that require explicit user confirmation or are blocked.
SENSITIVE_TABLES = {"audit_logs", "scheduled_tasks"}


def _extract_table_references(query: str) -> List[str]:
    """Naively extract table names referenced in a SELECT query.

    This is intentionally simple: it looks for FROM/JOIN clauses and
    returns the following bare word. It does not need to parse full SQL.
    """
    import re
    refs = []
    for match in re.finditer(r"\b(?:FROM|JOIN)\s+([A-Za-z_][A-Za-z0-9_]*)\b", query, re.IGNORECASE):
        refs.append(match.group(1).lower())
    return refs


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

    # Rate-limit this tool to avoid abuse.
    from zeus.security.rate_limit import get_execution_limiter
    from zeus.tools.sandbox_client import current_user_session

    limiter = get_execution_limiter()
    user_id, session_id = current_user_session()
    if not limiter.is_allowed("query_database", user_id=user_id, session_id=session_id):
        return {"error": "Rate limit exceeded for query_database. Try again later."}

    # Restrict access to sensitive tables.
    table_refs = _extract_table_references(safe_query)
    for table in table_refs:
        if table in SENSITIVE_TABLES:
            return {"error": f"Access to table '{table}' is not allowed via query_database."}
        if table not in ALLOWED_TABLES:
            return {"error": f"Table '{table}' is not in the query_database allowlist."}

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
    tags=["database", "read"],
)
