"""Unit tests for reasoning memory."""

from zeus.memory.reasoning import ReasoningMemory


def test_reasoning_memory_save_and_recall():
    mem = ReasoningMemory()
    mem.clear()

    mem.save("deploy app", "check git status, then push", "deployed successfully", tags=["deploy"])
    entries = mem.recall("deploy")

    assert len(entries) == 1
    assert entries[0]["task"] == "deploy app"
    assert entries[0]["outcome"] == "deployed successfully"

    mem.clear()


def test_reasoning_memory_avoids_duplicates():
    mem = ReasoningMemory()
    mem.clear()

    mem.save("task", "reasoning", "ok")
    mem.save("task", "reasoning", "ok")
    entries = mem.recall("task")

    assert len(entries) == 1
    mem.clear()


def test_reasoning_memory_isolated_by_user():
    mem_a = ReasoningMemory(user_id="user-a")
    mem_b = ReasoningMemory(user_id="user-b")
    mem_a.clear()
    mem_b.clear()

    mem_a.save("deploy", "use git", "ok")
    mem_b.save("deploy", "use ftp", "ok")

    assert len(mem_a.recall("deploy")) == 1
    assert mem_a.recall("deploy")[0]["reasoning"] == "use git"
    assert mem_b.recall("deploy")[0]["reasoning"] == "use ftp"

    mem_a.clear()
    mem_b.clear()


def test_reasoning_memory_keyword_fallback():
    mem = ReasoningMemory(user_id="keyword-test")
    mem.clear()

    mem.save("fix bug", "check logs and restart", "fixed")
    results = mem.recall("logs")

    assert len(results) == 1
    assert "logs" in results[0]["reasoning"]

    mem.clear()
