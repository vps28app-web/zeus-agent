"""Unit tests for zeus/memory/session_log.py."""

import json
from unittest.mock import MagicMock, patch

from zeus.memory import session_log


def test_logger_creates_jsonl(tmp_path, monkeypatch):
    monkeypatch.setenv("ZEUS_HOME", str(tmp_path))
    logger = session_log.SessionLogger(session_id="s1")
    logger.log_turn("user", "hello")

    log_file = tmp_path / "logs" / "s1.jsonl"
    assert log_file.exists()
    lines = log_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["role"] == "user"
    assert entry["content"] == "hello"
    assert entry["session_id"] == "s1"


def test_logger_appends_metadata(tmp_path, monkeypatch):
    monkeypatch.setenv("ZEUS_HOME", str(tmp_path))
    logger = session_log.SessionLogger(session_id="s2")
    logger.log_turn("assistant", "hi", metadata={"model": "gpt-4o"})

    log_file = tmp_path / "logs" / "s2.jsonl"
    entry = json.loads(log_file.read_text(encoding="utf-8").strip().splitlines()[0])
    assert entry["metadata"]["model"] == "gpt-4o"


def test_get_logger_new_session(tmp_path, monkeypatch):
    monkeypatch.setenv("ZEUS_HOME", str(tmp_path))
    logger = session_log.get_logger(new_session=True)
    assert logger.session_id is not None


def test_get_session_messages(tmp_path, monkeypatch):
    monkeypatch.setenv("ZEUS_HOME", str(tmp_path))
    logger = session_log.SessionLogger(session_id="s3")
    logger.log_turn("user", "q1")
    logger.log_turn("assistant", "a1")
    logger.log_turn("tool", {"result": "x"})

    messages = session_log.get_session_messages("s3")
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[1]["role"] == "assistant"


def test_get_session_messages_limit(tmp_path, monkeypatch):
    monkeypatch.setenv("ZEUS_HOME", str(tmp_path))
    logger = session_log.SessionLogger(session_id="s4")
    for i in range(5):
        logger.log_turn("user", f"q{i}")
        logger.log_turn("assistant", f"a{i}")

    messages = session_log.get_session_messages("s4", limit=3)
    assert len(messages) == 3


def test_get_session_messages_missing_session(tmp_path, monkeypatch):
    monkeypatch.setenv("ZEUS_HOME", str(tmp_path))
    assert session_log.get_session_messages("missing") == []


def test_list_sessions_from_sqlite(tmp_path, monkeypatch):
    monkeypatch.setenv("ZEUS_HOME", str(tmp_path))
    monkeypatch.setenv("ZEUS_USE_SQLITE", "true")
    repo = MagicMock()
    repo.list_sessions.return_value = ["s5", "s6"]
    with patch("zeus.memory.session_log.SessionRepository", return_value=repo):
        logger = session_log.SessionLogger(session_id="s5")
        sessions = logger.list_sessions()
    assert "s5" in sessions
    assert "s6" in sessions


def test_list_sessions_from_disk(tmp_path, monkeypatch):
    monkeypatch.setenv("ZEUS_HOME", str(tmp_path))
    monkeypatch.setenv("ZEUS_USE_SQLITE", "false")
    logger = session_log.SessionLogger(session_id="s7")
    logger.log_turn("user", "x")
    sessions = logger.list_sessions()
    assert "s7" in sessions
