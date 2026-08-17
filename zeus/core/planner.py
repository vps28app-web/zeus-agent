"""Plan mode: ask the LLM to produce a structured plan before executing."""

import json
import os
from typing import Any, Dict, List, Optional

from zeus.core.router import chat
from zeus.core.registry import REGISTRY


PLAN_SYSTEM_PROMPT = """You are Zeus in planning mode.

Given a user request, produce a concise step-by-step plan. Each step must be:
- Actionable by an agent that has access to terminal, file, web, code, git and memory tools.
- Short (one sentence).
- Numbered.

Respond ONLY with a JSON object in this exact format:
{
  "title": "short plan title",
  "steps": [
    {"step": 1, "action": "describe what to do", "tool_hint": "optional tool name or 'any'"},
    ...
  ],
  "estimated_steps": 3
}

Do not add markdown, explanation or commentary outside the JSON."""


def generate_plan(request: str, provider: Optional[str] = None, model: Optional[str] = None) -> Dict[str, Any]:
    """Ask the LLM to generate a structured plan for the request."""
    messages = [
        {"role": "system", "content": PLAN_SYSTEM_PROMPT},
        {"role": "user", "content": f"Create a plan for: {request}"},
    ]
    response = chat(messages, tools=[], provider=provider, model=model)
    content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
    content = content.strip()
    if content.startswith("```"):
        content = content.split("\n", 1)[1].rsplit("\n", 1)[0]
        content = content.removeprefix("json").strip()

    try:
        plan = json.loads(content)
    except json.JSONDecodeError:
        # Fallback: try to extract a JSON block from the text.
        start = content.find("{")
        end = content.rfind("}")
        if start != -1 and end != -1:
            plan = json.loads(content[start : end + 1])
        else:
            raise ValueError(f"Could not parse plan response: {content}")

    # Normalize steps.
    steps = plan.get("steps", [])
    normalized: List[Dict[str, Any]] = []
    for i, step in enumerate(steps, start=1):
        normalized.append({
            "step": step.get("step", i),
            "action": str(step.get("action", "")),
            "tool_hint": step.get("tool_hint", "any"),
        })
    plan["steps"] = normalized
    return plan


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
