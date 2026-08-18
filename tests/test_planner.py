"""Tests for the planner module."""

from zeus.core.planner import generate_bmad_plan


def test_generate_bmad_plan_structure():
    idea = "plataforma de delivery de plantas"
    plan = generate_bmad_plan(idea)

    assert plan["title"] == f"BMAD: {idea}"
    steps = plan["steps"]
    assert len(steps) == 10
    assert steps[0]["step"] == 1
    assert "proposta de valor" in steps[0]["action"].lower()
    assert steps[-1]["step"] == 10
    assert "sintetizar" in steps[-1]["action"].lower()
    assert all("action" in s and "tool_hint" in s for s in steps)
