"""Core agent loop: ReAct pattern (reason -> act -> observe)."""

import json
import time
import traceback
from typing import Any, Dict, List, Optional

from zeus.core.registry import REGISTRY
from zeus.core.router import chat
from zeus.core.schemas import AgentDecision, PlanOutput
from zeus.memory.reasoning import ReasoningMemory
from zeus.observability import get_metrics, get_tracer, report_summary


SYSTEM_PROMPT = """You are Zeus, an autonomous agent harness that solves tasks by using tools.

Your operating model is ReAct: think, act, observe, repeat until the task is done.

## Critical Output Rule

You MUST respond with a single valid JSON object matching this exact schema:
{
  "reasoning": "brief internal reasoning",
  "response": "your direct answer to the user (null if calling tools)",
  "tool_calls": [
    {"name": "tool_name", "arguments": {"key": "value"}}
  ]
}

- If you need to use a tool, set `response` to null and provide one or more `tool_calls`.
- If you are done, set `tool_calls` to [] and provide a natural-language `response`.
- Never include markdown, explanation or any text outside the JSON object.

## Rules

1. **Use tools for facts and actions.** Never invent filesystem contents, command outputs, URLs, or search results. Always call a tool to verify the real state.
2. **Plan before acting.** For multi-step tasks, briefly state your plan in `reasoning`, then execute one step at a time.
3. **Use the right tool for the job.** Prefer:
   - `run_sandboxed`, `execute_python`, `execute_shell_script` for risky or unknown code.
   - `run_terminal` only when you need host access or trust the command.
   - `git_*` tools for repository operations.
   - `browser_*` tools for interactive web pages; `web_search`/`web_extract` for quick lookup.
4. **One tool call per reasoning step is usually enough.** Wait for the result before deciding the next step.
5. **Be concise.** Explain why you are calling a tool in `reasoning`, then summarize the result.
6. **Cite outputs.** When giving a final answer, reference the tool outputs that support it.
7. **Stop when done.** If you have a final answer, do not call more tools.
8. **Replan on failure.** If a tool returns an error or unexpected result, explain what went wrong in `reasoning` and choose a different approach.
9. **Learn from reasoning.** When you successfully solve a task, your reasoning may be saved to help with similar future tasks.
"""


def _parse_decision(content: Optional[str]) -> AgentDecision:
    """Parse the LLM response into a structured AgentDecision."""
    if not content:
        return AgentDecision(reasoning="empty response", response="No response.")

    text = content.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("\n", 1)[0]
        text = text.removeprefix("json").strip()

    try:
        return AgentDecision.model_validate_json(text)
    except Exception as e:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return AgentDecision.model_validate_json(text[start : end + 1])
            except Exception:
                pass
        return AgentDecision(
            reasoning=f"failed to parse model response: {e}",
            response=text,
        )


def _tool_calls_from_decision(decision: AgentDecision) -> List[Dict[str, Any]]:
    """Convert AgentDecision tool_calls to OpenAI-like tool_calls format."""
    calls = []
    for i, call in enumerate(decision.tool_calls):
        calls.append({
            "id": f"call_{i}",
            "type": "function",
            "function": {
                "name": call.name,
                "arguments": json.dumps(call.arguments),
            },
        })
    return calls


def normalize_tool_calls(response: Dict[str, Any]) -> tuple[Optional[AgentDecision], Optional[str]]:
    """Extract structured decision and raw content from LLM response."""
    message = response.get("choices", [{}])[0].get("message", {})
    content: Optional[str] = message.get("content")

    # If model used native tool_calls, return them directly.
    native_calls = message.get("tool_calls")
    if native_calls:
        return None, content

    decision = _parse_decision(content)
    return decision, content


def execute_tool_call(call: Dict[str, Any], metrics, tracer) -> Dict[str, Any]:
    name = call.get("function", {}).get("name")
    arguments = call.get("function", {}).get("arguments", "{}")
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError:
            metrics.record_tool_call(name or "unknown", 0, error=True, result_summary="Invalid JSON arguments")
            return {"error": f"Invalid JSON arguments for tool {name}"}

    tool = REGISTRY.get(name)
    if not tool:
        metrics.record_tool_call(name or "unknown", 0, error=True, result_summary="Tool not found")
        return {"error": f"Tool not found: {name}"}

    span = tracer.start_span("tool_call", {"tool": name, "arguments": arguments})
    start = time.time()
    try:
        result = tool.handler(**arguments)
        latency_ms = (time.time() - start) * 1000
        summary = json.dumps(result)[:200]
        metrics.record_tool_call(name, latency_ms, error=False, result_summary=summary)
        span.finish(status="ok", attributes={"latency_ms": latency_ms, "result_summary": summary})
        return {"tool": name, "result": result}
    except Exception as e:
        latency_ms = (time.time() - start) * 1000
        metrics.record_tool_call(name, latency_ms, error=True, result_summary=str(e))
        span.finish(status="error", attributes={"latency_ms": latency_ms, "error": str(e)})
        return {"tool": name, "error": str(e), "traceback": traceback.format_exc()}


def _parse_plan(content: str) -> PlanOutput:
    """Parse LLM response into a structured PlanOutput for replanning."""
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


def _generate_replan(
    user_input: str,
    failed_tool: str,
    error: str,
    history_summary: str,
    messages: List[Dict[str, Any]],
) -> str:
    """Ask the LLM for a short replan after a tool failure."""
    prompt = f"""The agent failed while executing a step.

Original task: {user_input}
Failed tool: {failed_tool}
Error: {error}
History: {history_summary}

Create a concise replan. Respond ONLY with a JSON object matching this schema:
{{"title": "replan title", "steps": [{{"step": 1, "action": "...", "tool_hint": "..."}}]}}
"""
    replan_messages = [
        {"role": "system", "content": "You are a replanning assistant. Output only valid JSON."},
        {"role": "user", "content": prompt},
    ]
    try:
        response = chat(replan_messages, tools=[])
        content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
        plan = _parse_plan(content)
        lines = [f"Replan: {plan.title}"]
        for step in plan.steps:
            lines.append(f"  {step.step}. {step.action} [{step.tool_hint}]")
        return "\n".join(lines)
    except Exception as e:
        return f"Replan failed: {e}. Try a different tool or adjust arguments."


def run_agent(
    user_input: str,
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
    platform: Optional[str] = None,
    max_turns: int = 20,
    stream: bool = False,
    stream_callback=None,
    tool_callback=None,
    enable_reasoning_memory: bool = True,
) -> str:
    metrics = get_metrics(session_id)
    tracer = get_tracer(session_id)
    tracer.start_span("run_agent", {"user_input": user_input})

    from zeus.memory.store import MemoryStore
    from zeus.memory.user_profile import UserProfileStore

    mem_store = MemoryStore()
    mem_context = mem_store.get_summary_context()

    profile_context = ""
    if user_id:
        profile_store = UserProfileStore()
        profile_store.learn_from_message(user_id, platform, user_input, role="user")
        profile_context = profile_store.format_context(user_id)

    reasoning_memory = ReasoningMemory(user_id=user_id) if enable_reasoning_memory else None
    reasoning_context = reasoning_memory.format_context(user_input) if reasoning_memory else ""

    system_prompt = SYSTEM_PROMPT
    if reasoning_context:
        system_prompt += f"\n\n{reasoning_context}\n"
    if profile_context:
        system_prompt += f"\n\n## User Profile\n{profile_context}\n"
    if mem_context:
        system_prompt += f"\n\n## Persistent User Profile & Knowledge\n{mem_context}\n"

    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_input},
    ]

    provider = None
    model = None
    last_reasoning = ""
    final_response = ""

    for turn in range(max_turns):
        from zeus.memory.context import prune_messages
        active_messages = prune_messages(messages)

        tools = REGISTRY.schemas()
        llm_start = time.time()
        llm_span = tracer.start_span("llm_call", {"turn": turn, "provider": provider, "model": model})
        try:
            response = chat(active_messages, tools, stream=stream, stream_callback=stream_callback)
            llm_latency_ms = (time.time() - llm_start) * 1000
            usage = response.get("usage", {})
            input_tokens = usage.get("prompt_tokens", 0) or usage.get("input_tokens", 0)
            output_tokens = usage.get("completion_tokens", 0) or usage.get("output_tokens", 0)
            provider = response.get("provider") or provider
            model = response.get("model") or model
            metrics.record_llm_call(llm_latency_ms, input_tokens, output_tokens)
            llm_span.finish(status="ok", attributes={"latency_ms": llm_latency_ms, "input_tokens": input_tokens, "output_tokens": output_tokens})
        except Exception as e:
            llm_latency_ms = (time.time() - llm_start) * 1000
            metrics.record_llm_call(llm_latency_ms, error=True)
            llm_span.finish(status="error", attributes={"latency_ms": llm_latency_ms, "error": str(e)})
            tracer.finish_span(status="error")
            return f"LLM error: {e}"

        decision, content = normalize_tool_calls(response)

        # Handle native tool_calls path.
        if decision is None:
            native_calls = response.get("choices", [{}])[0].get("message", {}).get("tool_calls") or []
            if not native_calls:
                final_response = content or "No response."
                break
            assistant_message = {"role": "assistant", "content": content or "", "tool_calls": native_calls}
            messages.append(assistant_message)
            for call in native_calls:
                if tool_callback:
                    fn_info = call.get("function", {})
                    tool_callback(fn_info.get("name"), fn_info.get("arguments"))
                result = execute_tool_call(call, metrics, tracer)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.get("id", "call_0"),
                        "name": call.get("function", {}).get("name"),
                        "content": json.dumps(result),
                    }
                )
                if isinstance(result, dict) and result.get("error"):
                    history_summary = " ".join(
                        f"{m.get('role')}: {str(m.get('content', ''))[:80]}"
                        for m in messages[-6:]
                    )
                    replan = _generate_replan(user_input, call.get("function", {}).get("name", ""), result["error"], history_summary, messages)
                    messages.append({"role": "system", "content": replan})
            continue

        # Structured JSON path.
        last_reasoning = decision.reasoning
        messages.append({"role": "assistant", "content": content or ""})

        if decision.response and not decision.tool_calls:
            final_response = decision.response
            break

        calls = _tool_calls_from_decision(decision)
        if not calls:
            final_response = decision.response or "No response."
            break

        assistant_message = {"role": "assistant", "content": content or "", "tool_calls": calls}
        messages.append(assistant_message)

        for call in calls:
            if tool_callback:
                fn_info = call.get("function", {})
                tool_callback(fn_info.get("name"), fn_info.get("arguments"))
            result = execute_tool_call(call, metrics, tracer)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.get("id", "call_0"),
                    "name": call.get("function", {}).get("name"),
                    "content": json.dumps(result),
                }
            )
            if isinstance(result, dict) and result.get("error"):
                history_summary = " ".join(
                    f"{m.get('role')}: {str(m.get('content', ''))[:80]}"
                    for m in messages[-6:]
                )
                failed_name = call.get("function", {}).get("name", "")
                replan = _generate_replan(user_input, failed_name, result["error"], history_summary, messages)
                messages.append({"role": "system", "content": replan})

    if final_response:
        if reasoning_memory and last_reasoning:
            reasoning_memory.save(user_input, last_reasoning, final_response)
        tracer.finish_span(status="ok")
        return final_response

    tracer.finish_span(status="error", attributes={"reason": "max_turns_reached"})
    return "Maximum turns reached."


def run_summary(session_id: Optional[str] = None) -> str:
    """Return a human-readable summary of the session."""
    metrics = get_metrics(session_id)
    summary = report_summary(metrics)
    from zeus.observability.reporter import format_summary
    return format_summary(summary)
