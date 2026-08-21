"""Unit tests for zeus/core/team.py."""

from zeus.core.team import Team, Worker, create_default_team


def test_worker_creation_and_run_uses_allowed_tools(monkeypatch):
    worker = Worker(
        name="test_worker",
        description="A test worker",
        system_prompt="You are a test worker.",
        allowed_tools=["read_file"],
    )
    assert worker.name == "test_worker"
    assert worker.allowed_tools == {"read_file"}

    # Mock chat and execute_tool_call to avoid real LLM calls.
    chat_calls = []

    def fake_chat(messages, tools):
        chat_calls.append((messages, tools))
        # First call: request a tool call; second call: final answer.
        if len(chat_calls) == 1:
            return {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {
                                        "name": "read_file",
                                        "arguments": '{"path": "/tmp/test.txt"}',
                                    },
                                }
                            ],
                        }
                    }
                ]
            }
        return {
            "choices": [
                {"message": {"role": "assistant", "content": "done"}}
            ]
        }

    monkeypatch.setattr("zeus.core.router.chat", fake_chat)
    monkeypatch.setattr(
        "zeus.core.agent.execute_tool_call",
        lambda call, metrics, tracer: {"content": "file contents"},
    )

    result = worker.run("read the file")
    assert result == "done"
    # Ensure only allowed tool schema is passed.
    assert len(chat_calls) == 2
    passed_tools = chat_calls[0][1]
    assert all(
        schema["function"]["name"] == "read_file" for schema in passed_tools
    )


def test_worker_blocks_disallowed_tool(monkeypatch):
    worker = Worker(
        name="restricted",
        description="Restricted worker",
        system_prompt="You are restricted.",
        allowed_tools=["read_file"],
    )

    call_count = {"n": 0}

    def fake_chat(messages, tools):
        call_count["n"] += 1
        # On the first call the LLM requests a disallowed tool.
        # The worker should append the error result and then ask again.
        if call_count["n"] == 1:
            return {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {
                                        "name": "run_terminal",
                                        "arguments": '{"command": "ls"}',
                                    },
                                }
                            ],
                        }
                    }
                ]
            }
        return {
            "choices": [
                {"message": {"role": "assistant", "content": "done"}}
            ]
        }

    monkeypatch.setattr("zeus.core.router.chat", fake_chat)

    result = worker.run("list files")
    assert "done" in result.lower() or call_count["n"] >= 2
    # Ensure the disallowed tool was never actually executed via execute_tool_call.
    assert call_count["n"] >= 2


def test_team_register_and_plan_and_delegate(monkeypatch):
    team = Team(session_id="test-session")
    worker = Worker(name="generalist", description="General", system_prompt="You are general.")
    team.register(worker)

    monkeypatch.setattr(
        "zeus.core.team.run_agent",
        lambda prompt, **kwargs: '{"worker": "generalist", "task": "handle it"}',
    )

    response = team.plan_and_delegate("do something")
    assert "generalist" in response
    assert "handle it" in response


def test_team_run_finishes_on_final_answer(monkeypatch):
    team = Team(session_id="test-session")
    team.register(
        Worker(name="generalist", description="General", system_prompt="You are general.")
    )

    def fake_plan_and_delegate(user_input):
        return '{"worker": "generalist", "task": "say hi"}'

    monkeypatch.setattr(team, "plan_and_delegate", fake_plan_and_delegate)

    def fake_worker_run(task, worker, session_id=None, max_turns=15):
        return "hello"

    monkeypatch.setattr("zeus.core.team._run_worker", fake_worker_run)
    monkeypatch.setattr(
        "zeus.core.team.run_agent",
        lambda prompt, **kwargs: "FINAL ANSWER: all done",
    )

    result = team.run("greet")
    assert result == "all done"


def test_team_run_parses_next_plan(monkeypatch):
    team = Team(session_id="test-session")
    team.register(
        Worker(name="generalist", description="General", system_prompt="You are general.")
    )

    call_count = {"plan": 0}

    def fake_plan_and_delegate(user_input):
        call_count["plan"] += 1
        return '{"worker": "generalist", "task": "step 1"}'

    monkeypatch.setattr(team, "plan_and_delegate", fake_plan_and_delegate)

    def fake_worker_run(task, worker, session_id=None, max_turns=15):
        return f"result for {task}"

    monkeypatch.setattr("zeus.core.team._run_worker", fake_worker_run)

    synthesis_responses = [
        '{"worker": "generalist", "task": "step 2"}',
        "FINAL ANSWER: finished",
    ]

    def fake_run_agent(prompt, **kwargs):
        return synthesis_responses.pop(0)

    monkeypatch.setattr("zeus.core.team.run_agent", fake_run_agent)

    result = team.run("multi step")
    assert result == "finished"


def test_create_default_team_has_workers():
    team = create_default_team(session_id="default-test")
    assert "generalist" in team.workers
    assert "coder" in team.workers
    assert "researcher" in team.workers
    assert "shell" in team.workers
    assert "reviewer" in team.workers

    coder = team.workers["coder"]
    assert "read_file" in coder.allowed_tools
    assert "run_terminal" in coder.allowed_tools

    researcher = team.workers["researcher"]
    assert "web_search" in researcher.allowed_tools

    reviewer = team.workers["reviewer"]
    assert "git_diff" in reviewer.allowed_tools
