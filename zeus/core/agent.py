"""Core agent loop: ReAct pattern (reason -> act -> observe)."""

import json
import re
import time
import traceback
from typing import Any, Dict, List, Optional

from zeus.core.registry import REGISTRY
from zeus.core.router import chat
from zeus.core.schemas import AgentDecision, PlanOutput, ToolCallDecision
from zeus.memory.learning import LearningStore
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
10. **Strict Tool Verification.** Only call tools explicitly provided in your active tools schema. If an MCP server or tool is disabled or removed, do not attempt to invoke it; use native tools instead.
11. **Learn from the past.** When facing a task, check if past learnings or reasoning memories provide a relevant solution pattern; prefer proven approaches.
12. **Execution modes are user commands, not your job.** The user switches execution modes themselves with slash commands in the CLI: `/mode sandbox`, `/mode terminal`, `/mode auto`, `/mode readonly`, `/mode dryrun`. If the user asks to change or check the mode, tell them to use `/mode <name>` (or `/mode status` to see the current one). Do NOT hunt through memory, the database, code files, or the .env to figure out how to change it, and do NOT call update_zeus_config to set ZEUS_EXECUTION_* — that is not how modes change and it produces wrong values. The mode is managed by the CLI, outside your tool loop.
"""



def _clean_model_artifacts(text: str) -> str:
    """Strip XML tool call tags and artifacts emitted by LLMs."""
    if not text:
        return ""
    cleaned = re.sub(r"</?(?:parameter|function|tool_call|invoke|tool_name)[^>]*>", "", text, flags=re.IGNORECASE)
    return cleaned.strip()


def clean_agent_response(text: str) -> str:
    """Clean raw JSON/XML metadata artifacts from LLM response text for presentation."""
    if not text or not isinstance(text, str):
        return ""

    cleaned = _clean_model_artifacts(text)

    # Check if cleaned text is raw JSON containing reasoning / response / tool_calls
    if ("\"reasoning\"" in cleaned or "\"response\"" in cleaned or "\"tool_calls\"" in cleaned) and ("{" in cleaned and "}" in cleaned):
        try:
            start = cleaned.find("{")
            end = cleaned.rfind("}")
            if start != -1 and end != -1 and end > start:
                data = json.loads(cleaned[start:end + 1])
                if isinstance(data, dict):
                    resp = data.get("response")
                    reasoning = data.get("reasoning")
                    if resp and isinstance(resp, str) and resp.strip() and resp.strip().lower() != "null":
                        return resp.strip()
                    if reasoning and isinstance(reasoning, str) and reasoning.strip():
                        return reasoning.strip()
        except Exception:
            resp_match = re.search(r'"response"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"', cleaned)
            if resp_match:
                val = resp_match.group(1).replace("\\n", "\n").replace('\\"', '"')
                if val.strip() and val.strip().lower() != "null":
                    return val.strip()
            reas_match = re.search(r'"reasoning"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"', cleaned)
            if reas_match:
                val = reas_match.group(1).replace("\\n", "\n").replace('\\"', '"')
                if val.strip():
                    return val.strip()

    # Remove code fence wrapper if it only wraps raw JSON
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if len(lines) >= 2 and lines[0].startswith("```"):
            cleaned = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])

    return cleaned.strip()


def _parse_decision(content: Optional[str]) -> AgentDecision:
    """Parse the LLM response into a structured AgentDecision."""
    if not content:
        return AgentDecision(reasoning="empty response", response="No response.")

    text = _clean_model_artifacts(content)
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("\n", 1)[0]
        text = text.removeprefix("json").strip()

    # 1. Try standard Pydantic JSON parsing
    try:
        return AgentDecision.model_validate_json(text)
    except Exception:
        pass

    # 2. Try substring JSON parsing with fallback mapping
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        json_str = text[start : end + 1]
        try:
            return AgentDecision.model_validate_json(json_str)
        except Exception:
            try:
                data = json.loads(json_str)
                if isinstance(data, dict):
                    reasoning = data.get("reasoning") or "Model reasoning"
                    response = data.get("response")
                    if isinstance(response, str) and (not response.strip() or response.strip().lower() == "null"):
                        response = None
                    raw_calls = data.get("tool_calls") or []
                    tool_calls = []
                    for item in raw_calls:
                        if isinstance(item, dict) and "name" in item:
                            tool_calls.append(ToolCallDecision(name=item["name"], arguments=item.get("arguments") or {}))
                    return AgentDecision(
                        reasoning=reasoning if isinstance(reasoning, str) else str(reasoning),
                        response=response if isinstance(response, str) else None,
                        tool_calls=tool_calls,
                    )
            except Exception:
                pass

    # 3. Fallback: extract clean human-readable response
    extracted_clean = clean_agent_response(text)
    return AgentDecision(
        reasoning="Extracted response",
        response=extracted_clean or text,
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


def execute_tool_call(call: Dict[str, Any], metrics, tracer, confirm_callback=None) -> Dict[str, Any]:
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

    # Validate tool call against Guardrails rules before execution
    from zeus.security.guardrails import GuardrailsManager
    guardrails = GuardrailsManager()
    block_res = guardrails.validate_tool_call(name or "", arguments if isinstance(arguments, dict) else {})
    if block_res:
        metrics.record_tool_call(name or "unknown", 0, error=True, result_summary=str(block_res))
        return {"tool": name, "result": block_res}

    # Basic schema validation: required keys and declared argument names.
    schema = tool.parameters
    if schema:
        args = arguments if isinstance(arguments, dict) else {}
        required = schema.get("required", [])
        missing = [k for k in required if k not in args]
        if missing:
            msg = f"Invalid arguments for tool '{name}': missing required keys {missing}"
            metrics.record_tool_call(name or "unknown", 0, error=True, result_summary=msg)
            return {"tool": name, "error": msg}
        if args:
            properties = schema.get("properties", {})
            extra = [k for k in args if k not in properties]
            if extra:
                msg = f"Invalid arguments for tool '{name}': unknown keys {extra}"
                metrics.record_tool_call(name or "unknown", 0, error=True, result_summary=msg)
                return {"tool": name, "error": msg}

    # Enforce read-only mode
    from zeus.security.permissions import get_global_permission_manager
    pm = get_global_permission_manager()
    if not pm.is_tool_allowed(name):
        msg = f"Tool '{name}' is blocked in read-only mode / ferramenta bloqueada no modo somente leitura."
        metrics.record_tool_call(name or "unknown", 0, error=True, result_summary=msg)
        return {"tool": name, "error": msg}

    # Enforce dry-run mode for mutating tools
    if pm.dry_run and name in pm.READ_ONLY_BLOCKED_TOOLS:
        summary = pm._format_tool_summary(name, arguments)
        sim_result = {
            "tool": name,
            "dry_run": True,
            "result": {
                "status": "simulated",
                "message": f"[DRY-RUN] {name} NÃO executado.\nComando/argumentos: {summary}\nImpacto esperado: a operação seria executada no ambiente real.",
            },
        }
        metrics.record_tool_call(name, 0, error=False, result_summary="dry-run simulation")
        return sim_result

    # Human-in-the-loop confirmation for terminal mode
    if pm.is_confirmation_required(name, arguments):
        if not pm.confirm_tool(name, arguments):
            msg = (
                f"Execution of '{name}' was denied by user / execução negada pelo usuário. "
                f"Stop and wait for the user's next instruction / pare e aguarde novas instruções."
            )
            metrics.record_tool_call(name or "unknown", 0, error=True, result_summary=msg)
            return {"tool": name, "error": msg, "execution_denied": True}

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
    tool_result_callback=None,
    enable_reasoning_memory: bool = True,
    tool_filter: Optional[set] = None,
) -> Any:
    metrics = get_metrics(session_id)
    tracer = get_tracer(session_id)
    tracer.start_span("run_agent", {"user_input": user_input, "tool_filter": sorted(tool_filter) if tool_filter else None})

    from zeus.security.guardrails import GuardrailsManager, GuardrailViolation
    guardrails = GuardrailsManager()
    try:
        user_input = guardrails.validate_input(user_input)
    except GuardrailViolation as gv:
        tracer.finish_span(status="error", attributes={"guardrail_violation": gv.rule})
        return f"Guardrail Blocked: {gv.message}"

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

    learning_store = LearningStore(user_id=user_id)
    learning_store.process_user_feedback(user_input, session_id=session_id)
    learning_context = learning_store.format_context(user_input)

    system_prompt = SYSTEM_PROMPT
    if reasoning_context:
        system_prompt += f"\n\n{reasoning_context}\n"
    if learning_context:
        system_prompt += f"\n\n{learning_context}\n"
    if profile_context:
        system_prompt += f"\n\n## User Profile\n{profile_context}\n"
    if mem_context:
        system_prompt += f"\n\n## Persistent User Profile & Knowledge\n{mem_context}\n"

    history_messages = []
    if session_id:
        from zeus.memory.session_log import get_session_messages
        history_messages = get_session_messages(session_id, limit=10)

    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
    ]
    messages.extend(history_messages)
    if not history_messages or history_messages[-1].get("content") != user_input:
        messages.append({"role": "user", "content": user_input})


    provider = None
    model = None
    last_reasoning = ""
    final_response = ""
    tool_call_history: List[str] = []

    try:
        for turn in range(max_turns):
            from zeus.memory.context import prune_messages
            active_messages = prune_messages(messages)

            tools = REGISTRY.schemas(tag_allowlist=tool_filter)
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
                    fn_name = call.get("function", {}).get("name")
                    fn_args = call.get("function", {}).get("arguments")
                    call_sig = f"{fn_name}:{fn_args}"
                    tool_call_history.append(call_sig)

                    if tool_callback:
                        tool_callback(fn_name, fn_args)
                    result = execute_tool_call(call, metrics, tracer)
                    if tool_result_callback:
                        tool_result_callback(fn_name, fn_args, result)
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.get("id", "call_0"),
                            "name": fn_name,
                            "content": json.dumps(result),
                        }
                    )
                    tool_res = result.get("result") if isinstance(result, dict) else None
                    if isinstance(tool_res, dict) and tool_res.get("permission_required"):
                        perm = tool_res["permission_required"]
                        tracer.finish_span(status="ok", attributes={"permission_required": perm})
                        return {
                            "permission_required": perm,
                            "pending_input": user_input,
                        }

                    # SSH password requested: propagate to CLI for secure prompt.
                    if isinstance(tool_res, dict) and tool_res.get("ssh_password_required"):
                        tracer.finish_span(status="ok", attributes={"ssh_password_required": True})
                        return {
                            "ssh_password_required": tool_res,
                            "pending_input": user_input,
                        }

                    # SSH user requested: propagate to CLI for a plain prompt.
                    if isinstance(tool_res, dict) and tool_res.get("ssh_user_required"):
                        tracer.finish_span(status="ok", attributes={"ssh_user_required": True})
                        return {
                            "ssh_user_required": tool_res,
                            "pending_input": user_input,
                        }

                    err_msg = result.get("error") or (tool_res.get("error") if isinstance(tool_res, dict) else None)
                    if err_msg:
                        if result.get("execution_denied"):
                            messages.append({
                                "role": "system",
                                "content": (
                                    f"The user explicitly DENIED execution of '{fn_name}'. "
                                    "You must STOP immediately, do not try the same or equivalent "
                                    "command through any other tool, and wait for the user's next message."
                                ),
                            })
                        else:
                            messages.append({
                                "role": "system",
                                "content": (
                                    f"The tool '{fn_name}' returned an error: {err_msg}. "
                                    "Replan: try a different tool, adjust arguments, or ask the user for clarification."
                                ),
                            })

                    # Check for repeated identical tool calls
                    if len(tool_call_history) >= 3 and tool_call_history[-3:] == [call_sig] * 3:
                        messages.append({
                            "role": "system",
                            "content": f"Loop Warning: You called '{fn_name}' 3 times in a row with identical arguments. Change your approach or provide final response.",
                        })

                continue

            # Structured JSON path.
            last_reasoning = decision.reasoning

            if decision.response and not decision.tool_calls:
                final_response = decision.response
                break

            calls = _tool_calls_from_decision(decision)
            if not calls:
                final_response = decision.response or decision.reasoning or "No response."
                break

            # Single assistant message carrying both content (if any) and tool_calls.
            assistant_message = {"role": "assistant", "content": content or "", "tool_calls": calls}
            messages.append(assistant_message)

            for call in calls:
                fn_name = call.get("function", {}).get("name")
                fn_args = call.get("function", {}).get("arguments")
                call_sig = f"{fn_name}:{fn_args}"
                tool_call_history.append(call_sig)

                if tool_callback:
                    tool_callback(fn_name, fn_args)
                result = execute_tool_call(call, metrics, tracer)
                if tool_result_callback:
                    tool_result_callback(fn_name, fn_args, result)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.get("id", "call_0"),
                        "name": fn_name,
                        "content": json.dumps(result),
                    }
                )
                tool_res = result.get("result") if isinstance(result, dict) else None
                if isinstance(tool_res, dict) and tool_res.get("permission_required"):
                    perm = tool_res["permission_required"]
                    tracer.finish_span(status="ok", attributes={"permission_required": perm})
                    return {
                        "permission_required": perm,
                        "pending_input": user_input,
                    }

                err_msg = result.get("error") or (tool_res.get("error") if isinstance(tool_res, dict) else None)
                if err_msg:
                    if result.get("execution_denied"):
                        messages.append({
                            "role": "system",
                            "content": (
                                f"The user explicitly DENIED execution of '{fn_name}'. "
                                "You must STOP immediately, do not try the same or equivalent "
                                "command through any other tool, and wait for the user's next message."
                            ),
                        })
                    else:
                        messages.append({
                            "role": "system",
                            "content": (
                                f"The tool '{fn_name}' failed with error: {err_msg}. "
                                "Replan: try a different tool, adjust arguments, or ask the user for clarification."
                            ),
                        })

                # Check for repeated identical tool calls
                if len(tool_call_history) >= 3 and tool_call_history[-3:] == [call_sig] * 3:
                    messages.append({
                        "role": "system",
                        "content": f"Loop Warning: You called '{fn_name}' 3 times in a row with identical arguments. Change your approach or provide final response.",
                    })

        if final_response:
            final_response = clean_agent_response(final_response)
            final_response = guardrails.sanitize_output(final_response)
            if reasoning_memory and last_reasoning:
                reasoning_memory.save(user_input, last_reasoning, final_response)
            if learning_store and session_id:
                try:
                    from zeus.memory.session_log import get_session_messages
                    turns = get_session_messages(session_id, limit=50)
                    learning_store.extract_from_session(session_id, turns)
                except Exception:
                    pass
            tracer.finish_span(status="ok")
            return final_response

        # Fallback summary if max turns reached
        try:
            messages.append({
                "role": "user",
                "content": "Maximum execution turns reached. Summarize what you have accomplished so far and provide your best final response.",
            })
            fallback_resp = chat(messages, tools=[])
            final_content = fallback_resp.get("choices", [{}])[0].get("message", {}).get("content", "")
            if final_content:
                final_response = guardrails.sanitize_output(final_content)
                tracer.finish_span(status="ok", attributes={"reason": "max_turns_summary_fallback"})
                return final_response
        except Exception:
            pass
    except KeyboardInterrupt:
        tracer.finish_span(status="error", attributes={"reason": "interrupted_by_user"})
        raise

    tracer.finish_span(status="error", attributes={"reason": "max_turns_reached"})
    return "Maximum turns reached."


def run_summary(session_id: Optional[str] = None) -> str:
    """Return a human-readable summary of the session."""
    metrics = get_metrics(session_id)
    summary = report_summary(metrics)
    from zeus.observability.reporter import format_summary
    return format_summary(summary)
