"""Additional unit tests for zeus/memory/reasoning.py."""

from unittest.mock import patch

import pytest

from zeus.memory.reasoning import ReasoningMemory


@pytest.fixture
def mem(tmp_path, monkeypatch):
    monkeypatch.setenv("ZEUS_HOME", str(tmp_path))
    return ReasoningMemory(user_id="u1")


def test_save_avoids_duplicates(mem):
    mem.save("task1", "reasoning1", "ok")
    mem.save("task1", "reasoning1", "ok")
    assert len(mem._load()) == 1


def test_recall_empty(mem):
    assert mem.recall("anything") == []


def test_recall_keyword_fallback(mem):
    mem.save("python task", "use requests library", "success", tags=["python"])
    results = mem.recall("python requests")
    assert len(results) == 1
    assert results[0]["task"] == "python task"


def test_recall_keyword_no_match(mem):
    mem.save("task", "reason", "ok")
    assert mem.recall("zzzzzzzz") == []


def test_recall_embedding_path(mem):
    fake_embedding = [0.1, 0.2, 0.3]
    mem.save("task", "reason", "ok")

    with patch.object(mem, "_embed_text", return_value=fake_embedding):
        results = mem.recall("task")

    # with same embedding for query and entry, cosine similarity is 1.0
    assert len(results) == 1


def test_format_context_empty(mem):
    assert mem.format_context("task") == ""


def test_format_context_with_entry(mem):
    mem.save("task", "reason", "ok")
    ctx = mem.format_context("task")
    assert "Past Reasoning Insights" in ctx


def test_clear(mem):
    mem.save("task", "reason", "ok")
    mem.clear()
    assert mem._load() == []
