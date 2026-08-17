"""Core agent loop: ReAct pattern (reason -> act -> observe)."""

import json
import time
import traceback
from typing import Any, Dict, List, Optional

from zeus.core.registry import REGISTRY
from zeus.core.router import chat
from zeus.observability import get_metrics, get_tracer, report_summary


SYSTEM_PROMPT = """You are Zeus, an autonomous agent harness that solves tasks by using tools.

Your operating model is ReAct: think, act, observe, repeat until the task is done.

## Rules

1. **Use tools for facts and actions.** Never invent filesystem contents, command outputs, URLs, or search results. Always call a tool to verify the real state.
2. **Plan before acting.** For multi-step tasks, briefly state your plan, then execute one step at a time.
3. **Use the right tool for the job.** Prefer:
   - `run_sandboxed`, `execute_python`, `execute_shell_script` for risky or unknown code.
   - `run_terminal` only when you need host access or trust the command.
   - `git_*` tools for repository operations.
   - `browser_*` tools for interactive web pages; `web_search`/`web_extract` for quick lookup.
4. **One tool call per reasoning step is usually enough.** Wait for the result before deciding the next step.
5. **Be concise.** Explain why you are calling a tool, then summarize the result.
6. **Cite outputs.** When giving a final answer, reference the tool outputs that support it.
7. **Stop when done.** If you have a final answer, do not call more tools.

## Output format

When calling a tool, respond with a short sentence explaining the action.
When giving the final answer, be direct and cite relevant outputs.

## Examples

User: "Quantos arquivos Python tem no projeto Zeus?"
Assistant: "Vou listar os arquivos Python no diretório do projeto." [calls list_directory/search_files]

User: "Execute Python para calcular a média de [1,2,3,4,5]."
Assistant: "Vou executar o cálculo de forma isolada na sandbox." [calls execute_python]

User: "Qual a última versão do Django?"
Assistant: "Vou pesquisar a última versão do Django." [calls web_search]
"""


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


def normalize_tool_calls(response: Dict[str, Any]) -> tuple[List[Dict[str, Any]], Optional[str]]:
    message = response.get("choices", [{}])[0].get("message", {})
    calls: List[Dict[str, Any]] = message.get("tool_calls") or []
    content: Optional[str] = message.get("content")

    # Handle Ollama tool_calls format
    if calls and isinstance(calls[0], dict) and "function" not in calls[0]:
        calls = [
            {
                "id": f"call_{i}",
                "function": {
                    "name": c.get("function", {}).get("name") or c.get("name"),
                    "arguments": json.dumps(c.get("function", {}).get("arguments") or c.get("arguments", {})),
                },
            }
            for i, c in enumerate(calls)
        ]

    return calls, content


def run_agent(
    user_input: str,
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
    platform: Optional[str] = None,
    max_turns: int = 20,
    stream: bool = False,
    stream_callback=None,
    tool_callback=None,
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
        # Learn from current message before responding.
        profile_store.learn_from_message(user_id, platform, user_input, role="user")
        profile_context = profile_store.format_context(user_id)

    system_prompt = SYSTEM_PROMPT
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
            # Try to infer provider/model from response
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

        calls, content = normalize_tool_calls(response)

        if content:
            messages.append({"role": "assistant", "content": content})

        if not calls:
            tracer.finish_span(status="ok")
            return content or "No response."

        assistant_message: Dict[str, Any] = {"role": "assistant", "content": content or "", "tool_calls": calls}
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

    tracer.finish_span(status="error", attributes={"reason": "max_turns_reached"})
    return "Maximum turns reached."


def run_summary(session_id: Optional[str] = None) -> str:
    """Return a human-readable summary of the session."""
    metrics = get_metrics(session_id)
    summary = report_summary(metrics)
    from zeus.observability.reporter import format_summary
    return format_summary(summary)
