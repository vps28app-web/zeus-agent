"""Tests for continuous learning system."""

import pytest

from zeus.memory.learning import LearningStore
from zeus.tools.learning_tools import (
    list_recent_learnings,
    rate_learning,
    reflect_on_resolution,
    search_past_learnings,
)


@pytest.fixture
def store(tmp_path):
    from zeus.db.connection import init_db
    from zeus.db.repository import LearningRepository

    db_path = tmp_path / "test.db"
    init_db(db_path)
    repo = LearningRepository(db_path=db_path)
    return LearningStore(user_id="test_user", repo=repo)


def test_save_and_search(store):
    store.save(
        problem="problema de teste",
        solution="solucao de teste",
        tags=["teste", "resolution"],
    )
    results = store.search("problema de teste")
    assert len(results) == 1
    assert results[0]["problem"] == "problema de teste"
    assert results[0]["solution"] == "solucao de teste"


def test_avoid_duplicate(store):
    store.save(problem="x", solution="y")
    store.save(problem="x", solution="y")
    results = store.search("x")
    assert len(results) == 1
    assert results[0]["effectiveness_score"] > 0


def test_rate_learning(store):
    store.save(problem="x", solution="y")
    entry = store.search("x")[0]
    store.rate(entry["id"], helpful=True)
    updated = store.search("x")[0]
    assert updated["effectiveness_score"] > entry["effectiveness_score"]


def test_extract_from_session(store):
    turns = [
        {"role": "user", "content": "liste arquivos"},
        {"role": "tool", "content": '{"tool": "run_terminal", "error": "comando invalido"}'},
        {"role": "assistant", "content": "vou tentar outra abordagem"},
        {"role": "tool", "content": '{"tool": "run_terminal", "result": {"stdout": "a.txt"}}'},
        {"role": "assistant", "content": "encontrado: a.txt"},
    ]
    result = store.extract_from_session("sessao-1", turns)
    assert result is not None
    assert "run_terminal" in result["tools_used"]
    assert "comando invalido" in result["failure_pattern"]


def test_reflect_tool():
    res = reflect_on_resolution(
        problem="erro ao conectar",
        solution="reiniciar servico",
        tools_used="run_terminal",
        tags="infra",
    )
    assert res["status"] == "success"
    assert res["learning_id"] > 0


def test_search_and_list_tools():
    reflect_on_resolution(problem="foo bar", solution="baz")
    search = search_past_learnings("foo bar")
    assert search["count"] >= 1
    recent = list_recent_learnings(limit=5)
    assert recent["count"] == 5


def test_rate_tool(store):
    store.save(problem="z", solution="w")
    entry = store.search("z")[0]
    res = rate_learning(entry["id"], helpful=True)
    assert res["status"] == "success"


def test_token_keyword_search(store):
    store.save(
        problem="Erro de conexao com banco sqlite na porta 5432",
        solution="Usar arquivo sqlite local em vez de socket TCP",
        tags=["database", "sqlite"],
    )
    # Search with different natural language phrasing
    results = store.search("como resolver o erro no banco sqlite")
    assert len(results) >= 1
    assert "sqlite" in results[0]["problem"].lower()


def test_process_user_feedback(store):
    store.save(problem="Configurar webhook", solution="Usar ngrok tunnel", effectiveness_score=1)
    entry = store.search("webhook")[0]
    initial_score = entry["effectiveness_score"]

    # Positive feedback
    fb_pos = store.process_user_feedback("ótimo, funcionou perfeitamente!")
    assert fb_pos is not None
    assert fb_pos["feedback_type"] == "positive"
    updated_pos = store.search("webhook")[0]
    assert updated_pos["effectiveness_score"] > initial_score

    # Negative feedback
    fb_neg = store.process_user_feedback("ficou errado, não deu certo")
    assert fb_neg is not None
    assert fb_neg["feedback_type"] == "negative"
    updated_neg = store.search("webhook")[0]
    assert updated_neg["effectiveness_score"] < updated_pos["effectiveness_score"]


def test_get_stats_and_delete(store):
    id1 = store.save(problem="p1", solution="s1", tags=["auto-learned", "test"], effectiveness_score=2)
    id2 = store.save(problem="p2", solution="s2", tags=["manual"], effectiveness_score=0)

    stats = store.get_stats()
    assert stats["total_learnings"] >= 2
    assert stats["high_effectiveness"] >= 1
    assert stats["auto_learned"] >= 1

    store.delete(id1)
    results = store.search("p1")
    assert len(results) == 0
