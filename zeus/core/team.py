"""Multi-agent team orchestration for Zeus.

A Team is a coordinator agent that can delegate tasks to specialized worker agents.
Each worker has its own system prompt and a focused toolset.
"""

import json
import time
from typing import Any, Dict, List, Optional

from zeus.core.agent import run_agent
from zeus.core.registry import REGISTRY
from zeus.observability import get_metrics, get_tracer


class Worker:
    """A specialized sub-agent with its own prompt and allowed tools."""

    def __init__(
        self,
        name: str,
        description: str,
        system_prompt: str,
        allowed_tools: Optional[List[str]] = None,
    ):
        self.name = name
        self.description = description
        self.system_prompt = system_prompt
        self.allowed_tools = set(allowed_tools or [])

    def run(self, task: str, session_id: Optional[str] = None, max_turns: int = 15) -> str:
        """Execute this worker's task using a constrained agent loop."""
        return _run_worker(
            task=task,
            worker=self,
            session_id=session_id,
            max_turns=max_turns,
        )


class Team:
    """Coordinator that selects workers and synthesizes their outputs."""

    def __init__(self, session_id: Optional[str] = None):
        self.session_id = session_id
        self.workers: Dict[str, Worker] = {}
        self.tracer = get_tracer(session_id)

    def register(self, worker: Worker) -> None:
        self.workers[worker.name] = worker

    def plan_and_delegate(self, user_input: str) -> str:
        """Use the coordinator to decide which workers to invoke."""
        worker_list = "\n".join(
            f"- {name}: {w.description}" for name, w in self.workers.items()
        )
        prompt = f"""You are the Zeus Team Coordinator. Your job is to delegate tasks to specialized workers.

Available workers:
{worker_list}

User request: {user_input}

Decide which worker should handle this task. If the task requires multiple skills, you may delegate sequentially.
Return ONLY a JSON object in this exact format:

{{"worker": "worker_name", "task": "clear and specific task description for the worker"}}

If no worker fits, return:
{{"worker": "generalist", "task": "original request"}}
"""
        response = run_agent(prompt, session_id=f"{self.session_id or 'team'}-coordinator", max_turns=3)
        return response

    def run(self, user_input: str, max_turns: int = 5) -> str:
        """Run the coordinator-worker loop."""
        span = self.tracer.start_span("team_run", {"user_input": user_input})
        context = user_input
        outputs: List[str] = []

        for turn in range(max_turns):
            plan_response = self.plan_and_delegate(context)
            try:
                # Try to extract JSON from the coordinator response.
                json_str = plan_response
                if "```json" in json_str:
                    json_str = json_str.split("```json")[1].split("```")[0]
                elif "```" in json_str:
                    json_str = json_str.split("```")[1].split("```")[0]
                plan = json.loads(json_str.strip())
            except Exception:
                # Fallback: treat the whole response as a generalist task.
                plan = {"worker": "generalist", "task": context}

            worker_name = plan.get("worker", "generalist")
            task = plan.get("task", context)

            if worker_name not in self.workers:
                worker_name = "generalist"
                task = context

            worker = self.workers[worker_name]
            worker_span = self.tracer.start_span("worker_run", {"worker": worker_name, "task": task})
            result = worker.run(task, session_id=f"{self.session_id or 'team'}-{worker_name}-{turn}")
            worker_span.finish(status="ok", attributes={"result_length": len(result)})

            outputs.append(f"### {worker_name}\n{result}")

            # Ask coordinator if we are done or need another worker.
            synthesis_prompt = f"""You are the Zeus Team Coordinator.

Original request: {user_input}

Worker '{worker_name}' produced this result:
{result}

Are we done? If yes, return a final concise answer to the user that synthesizes the result.
If we need another worker, return ONLY a JSON object:
{{"worker": "worker_name", "task": "next task description"}}

If no further work is needed, start your response with "FINAL ANSWER:".
"""
            synthesis = run_agent(synthesis_prompt, session_id=f"{self.session_id or 'team'}-coordinator", max_turns=3)

            if "FINAL ANSWER:" in synthesis:
                final = synthesis.split("FINAL ANSWER:", 1)[1].strip()
                span.finish(status="ok", attributes={"turns": turn + 1})
                return final

            # Otherwise, try to parse next plan.
            try:
                json_str = synthesis
                if "```json" in json_str:
                    json_str = json_str.split("```json")[1].split("```")[0]
                elif "```" in json_str:
                    json_str = json_str.split("```")[1].split("```")[0]
                plan = json.loads(json_str.strip())
                context = plan.get("task", user_input)
            except Exception:
                span.finish(status="ok", attributes={"turns": turn + 1})
                return synthesis

        final = "\n\n".join(outputs)
        span.finish(status="error", attributes={"reason": "max_turns_reached"})
        return f"Maximum team turns reached. Partial results:\n\n{final}"


def _run_worker(
    task: str,
    worker: Worker,
    session_id: Optional[str] = None,
    max_turns: int = 15,
) -> str:
    """Run a constrained agent loop for a worker."""
    from zeus.core.router import chat

    metrics = get_metrics(session_id)
    tracer = get_tracer(session_id)
    tracer.start_span("run_worker", {"worker": worker.name, "task": task})

    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": worker.system_prompt},
        {"role": "user", "content": task},
    ]

    # Build tool schemas filtered to allowed tools.
    if worker.allowed_tools:
        tools = [
            schema
            for schema in REGISTRY.schemas()
            if schema.get("function", {}).get("name") in worker.allowed_tools
        ]
    else:
        tools = REGISTRY.schemas()

    for turn in range(max_turns):
        llm_start = time.time()
        try:
            response = chat(messages, tools)
            llm_latency_ms = (time.time() - llm_start) * 1000
            usage = response.get("usage", {})
            metrics.record_llm_call(
                llm_latency_ms,
                usage.get("prompt_tokens", 0) or usage.get("input_tokens", 0),
                usage.get("completion_tokens", 0) or usage.get("output_tokens", 0),
            )
        except Exception as e:
            tracer.finish_span(status="error")
            return f"Worker LLM error: {e}"

        message = response.get("choices", [{}])[0].get("message", {})
        calls = message.get("tool_calls") or []
        content = message.get("content")

        if content:
            messages.append({"role": "assistant", "content": content})

        if not calls:
            tracer.finish_span(status="ok")
            return content or "No response."

        messages.append({"role": "assistant", "content": content or "", "tool_calls": calls})

        for call in calls:
            name = call.get("function", {}).get("name")
            if worker.allowed_tools and name not in worker.allowed_tools:
                result = {"error": f"Tool {name} not allowed for worker {worker.name}"}
            else:
                from zeus.core.agent import execute_tool_call
                result = execute_tool_call(call, metrics, tracer)
            messages.append({
                "role": "tool",
                "tool_call_id": call.get("id", "call_0"),
                "name": name,
                "content": json.dumps(result),
            })

    tracer.finish_span(status="error", attributes={"reason": "max_turns_reached"})
    return "Worker maximum turns reached."


# Predefined workers for common tasks.

def create_default_team(session_id: Optional[str] = None) -> Team:
    """Create a team with common worker roles."""
    team = Team(session_id=session_id)

    team.register(Worker(
        name="generalist",
        description="General-purpose agent that can use any tool and handle miscellaneous tasks.",
        system_prompt="""You are a general-purpose agent. Use the available tools to help the user.
Be concise, accurate, and cite tool outputs. If a task is outside your tools, say so.""",
    ))

    team.register(Worker(
        name="coder",
        description="Writes, reads, and edits code and configuration files. Uses file and terminal tools.",
        system_prompt="""You are a senior software engineer. Your job is to read, write, and modify code.
Follow best practices: keep changes minimal, add tests when relevant, and explain what you changed.
Always verify files after writing them.""",
        allowed_tools=[
            "read_file", "write_file", "list_directory", "search_files",
            "run_terminal", "run_sandboxed", "execute_python", "git_status", "git_diff",
        ],
    ))

    team.register(Worker(
        name="researcher",
        description="Searches the web and extracts information from URLs.",
        system_prompt="""You are a research assistant. Search the web, extract relevant pages, and summarize findings.
Always cite sources and prefer recent or authoritative results.""",
        allowed_tools=["web_search", "web_extract", "browser_navigate", "browser_extract"],
    ))

    team.register(Worker(
        name="shell",
        description="Runs safe shell commands and Python scripts, preferably inside the sandbox.",
        system_prompt="""You are a system operations assistant. Run commands to inspect or transform the system.
Prefer the sandboxed tools (`run_sandboxed`, `execute_python`, `execute_shell_script`) for anything risky.
Explain the output clearly.""",
        allowed_tools=[
            "run_terminal", "run_sandboxed", "execute_python", "execute_shell_script",
            "read_file", "list_directory",
        ],
    ))

    team.register(Worker(
        name="reviewer",
        description="Reviews code, diffs, and outputs for quality, bugs, and security issues.",
        system_prompt="""You are a code reviewer. Analyze code, diffs, or outputs and report issues.
Focus on correctness, security, maintainability, and clarity. Be specific and cite line numbers when possible.""",
        allowed_tools=["read_file", "git_diff", "search_files"],
    ))

    return team
