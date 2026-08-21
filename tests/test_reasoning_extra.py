"""Additional unit tests for zeus/memory/reasoning.py using mocked repo."""

import json
from unittest.mock import MagicMock

from zeus.memory.reasoning import ReasoningMemory


def test_save_and_recall_keyword_fallback():
    repo = MagicMock()
    repo.get.return_value = []
    memory = ReasoningMemory(user_id="u1", repo=repo)

    memory.save("deploy app", "use docker", "success", tags=["deploy"])
    stored = [call[0][1] for call in repo.add.call_args_list]
    repo.get.return_value = stored

    results = memory.recall("deploy docker", limit=3)
    assert len(results) == 1
    assert results[0]["task"] == "deploy app"


def test_save_skips_duplicate():
    repo = MagicMock()
    existing = json.dumps({"task": "t", "reasoning": "r", "outcome": "o", "tags": []})
    repo.get.return_value = [existing]
    memory = ReasoningMemory(user_id="u2", repo=repo)

    memory.save("t", "r", "o")
    assert repo.add.call_count == 0


def test_recall_filters_zero_scores():
    repo = MagicMock()
    repo.get.return_value = [
        json.dumps({"task": "unrelated", "reasoning": "zzz", "outcome": "ok"})
    ]
    memory = ReasoningMemory(user_id="u3", repo=repo)
    results = memory.recall("deploy app")
    assert results == []


def test_format_context_returns_string():
    repo = MagicMock()
    repo.get.return_value = [
        json.dumps({"task": "t", "reasoning": "r", "outcome": "o"})
    ]
    memory = ReasoningMemory(user_id="u4", repo=repo)
    context = memory.format_context("t")
    assert "Past Reasoning Insights" in context
    assert "r" in context


def test_clear_calls_repo_clear():
    repo = MagicMock()
    memory = ReasoningMemory(user_id="u5", repo=repo)
    memory.clear()
    repo.clear.assert_called_once_with("reasoning_memory:u5")


def test_cosine_similarity_orthogonal():
    memory = ReasoningMemory()
    assert memory._cosine_similarity([1, 0], [0, 1]) == 0.0
    assert memory._cosine_similarity([1, 0], [1, 0]) == 1.0


def test_semantic_score_empty_query():
    memory = ReasoningMemory()
    score = memory._semantic_score("", {"task": "x"})
    assert score == 0.0
