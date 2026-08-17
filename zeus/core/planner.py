"""Plan mode: ask the LLM to produce a structured plan before executing."""

import json
import os
from typing import Any, Dict, List, Optional

from zeus.core.router import chat
from zeus.core.schemas import PlanOutput, PlanStep


PLAN_SYSTEM_PROMPT = """You are Zeus in planning mode.

Given a user request, produce a concise step-by-step plan.

You MUST respond with a single valid JSON object matching this exact schema:
{
  "title": "short plan title",
  "steps": [
    {"step": 1, "action": "describe what to do", "tool_hint": "optional tool name or 'any'"}
  ]
}

Do not add markdown, explanation or any text outside the JSON object."""


def _parse_plan(content: str) -> PlanOutput:
    """Parse LLM response into a structured PlanOutput."""
    text = content.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("\n", 1)[0]
        text = text.removeprefix("json").strip()

    try:
        return PlanOutput.model_validate_json(text)
    except Exception:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return PlanOutput.model_validate_json(text[start : end + 1])
            except Exception:
                pass
        raise ValueError(f"Could not parse plan response: {content}")


def generate_plan(
    request: str,
    provider: Optional[str] = None,
    model: Optional[str] = None,
) -> Dict[str, Any]:
    """Ask the LLM to generate a structured plan for the request."""
    messages = [
        {"role": "system", "content": PLAN_SYSTEM_PROMPT},
        {"role": "user", "content": f"Create a plan for: {request}"},
    ]
    response = chat(messages, tools=[], provider=provider, model=model)
    content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
    plan = _parse_plan(content)

    # Normalize steps.
    normalized: List[Dict[str, Any]] = []
    for i, step in enumerate(plan.steps, start=1):
        normalized.append({
            "step": step.step or i,
            "action": step.action,
            "tool_hint": step.tool_hint,
        })
    return {
        "title": plan.title,
        "steps": normalized,
    }


def execute_plan_step(
    step: Dict[str, Any],
    original_request: str,
    previous_results: List[Dict[str, Any]],
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
    platform: Optional[str] = None,
) -> Dict[str, Any]:
    """Execute a single plan step using the agent."""
    from zeus.core.agent import run_agent

    context = "\n\n".join(
        f"Step {r['step']} result:\n{r['result']}"
        for r in previous_results
    )

    prompt = f"""Original request: {original_request}

You are executing step {step['step']} of the plan:
{step['action']}

Execute this step only. Use the appropriate tool if needed. Be concise and report the outcome.
"""
    if context:
        prompt += f"\n\nContext from previous steps:\n{context}\n"

    result = run_agent(
        prompt,
        session_id=session_id,
        user_id=user_id,
        platform=platform,
    )
    return {"step": step["step"], "action": step["action"], "result": result}
