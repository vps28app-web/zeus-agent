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


def test_reasoning_memory_format_context():
    mem = ReasoningMemory()
    mem.clear()

    mem.save("test task", "think step by step", "success")
    context = mem.format_context("test task")

    assert "Past Reasoning Insights" in context
    assert "think step by step" in context
    mem.clear()
