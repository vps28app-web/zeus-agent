"""Unit tests for zeus/tools/database.py."""

import pytest

from zeus.db.connection import get_connection, init_db
from zeus.tools.database import query_database


@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "test.db"
    init_db(path)
    return path


@pytest.fixture
def patch_db_path(db_path, monkeypatch):
    from zeus.db import connection

    original = connection.get_db_path
    connection.get_db_path = lambda: db_path
    yield
    connection.get_db_path = original


def test_query_database_select(patch_db_path):
    res = query_database("SELECT 1 AS one, 2 AS two")
    assert res["columns"] == ["one", "two"]
    assert res["rows"] == [{"one": 1, "two": 2}]


def test_query_database_blocks_non_select(patch_db_path):
    res = query_database("DELETE FROM sessions")
    assert "error" in res


def test_query_database_blocks_multiple_statements(patch_db_path):
    res = query_database("SELECT 1; SELECT 2;")
    assert "error" in res


def test_query_database_with_params(patch_db_path):
    res = query_database("SELECT ? AS value", params=["hello"])
    assert res["rows"] == [{"value": "hello"}]


def test_query_database_honors_limit(patch_db_path):
    conn = get_connection()
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS numbers (value INTEGER)")
        conn.executemany("INSERT INTO numbers (value) VALUES (?)", [(i,) for i in range(1, 11)])
        conn.commit()
    finally:
        conn.close()

    res = query_database("SELECT value FROM numbers ORDER BY value", limit=3)
    assert res["row_count"] == 3
