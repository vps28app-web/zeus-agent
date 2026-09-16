"""Integration tests for the agent loop with a mocked LLM."""

import json
from unittest.mock import patch

from zeus.core.agent import run_agent
from zeus.core.registry import REGISTRY


def test_agent_no_tool_call():
    mock_response = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "Final answer.",
                    "tool_calls": None,
                }
            }
        ]
    }

    with patch("zeus.core.agent.chat", return_value=mock_response):
        result = run_agent("hello")
        assert result == "Final answer."


def test_agent_with_terminal_tool():
    tool = REGISTRY.get("run_terminal")
    assert tool is not None

    mock_response_1 = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "function": {
                                "name": "run_terminal",
                                "arguments": json.dumps({"command": "echo test"}),
                            },
                        }
                    ],
                }
            }
        ]
    }

    mock_response_2 = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "Done.",
                    "tool_calls": None,
                }
            }
        ]
    }

    with patch("zeus.core.agent.chat", side_effect=[mock_response_1, mock_response_2]):
        result = run_agent("run echo test")
        assert result == "Done."


def test_agent_permission_required_returns_dict(tmp_path):
    target_file = tmp_path / "protected.txt"
    mock_response = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_write",
                            "function": {
                                "name": "write_file",
                                "arguments": json.dumps({"path": str(target_file), "content": "secret"}),
                            },
                        }
                    ],
                }
            }
        ]
    }

    from zeus.security.permissions import PermissionManager
    from zeus.tools.file import set_file_permission_manager

    # Force read_only permission level with no callback so write fails and signals permission_required.
    pm = PermissionManager(file_level="read_only")
    set_file_permission_manager(pm)

    with patch("zeus.core.agent.chat", return_value=mock_response):
        result = run_agent("write to protected.txt")
        assert isinstance(result, dict)
        assert "permission_required" in result
        assert result["permission_required"]["action"] == "write"
        assert result["permission_required"]["path"] == str(target_file.resolve())
        assert result["pending_input"] == "write to protected.txt"


def test_agent_max_turns_summary_fallback():
    mock_tool_call_resp = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_loop",
                            "function": {
                                "name": "read_file",
                                "arguments": json.dumps({"path": "/tmp/non_existent.txt"}),
                            },
                        }
                    ],
                }
            }
        ]
    }

    mock_summary_resp = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "Summary: I attempted to read the file multiple times but it did not exist.",
                }
            }
        ]
    }

    with patch("zeus.core.agent.chat", side_effect=[mock_tool_call_resp, mock_tool_call_resp, mock_summary_resp]):
        result = run_agent("read file", max_turns=2)
        assert "Summary: I attempted to read the file" in result


def test_agent_tool_result_callback(tmp_path):
    from zeus.security.permissions import PermissionManager
    from zeus.tools.file import set_file_permission_manager

    target_file = (tmp_path / "hello.py").resolve()
    pm = PermissionManager(file_level="unrestricted")
    set_file_permission_manager(pm)

    callbacks_received = []

    def result_cb(name, args, result):
        callbacks_received.append((name, result))

    mock_resp_1 = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "function": {
                                "name": "write_file",
                                "arguments": json.dumps({"path": str(target_file), "content": "print('hello')\n"}),
                            },
                        }
                    ],
                }
            }
        ]
    }
    mock_resp_2 = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "File created successfully.",
                }
            }
        ]
    }

    with patch("zeus.core.agent.chat", side_effect=[mock_resp_1, mock_resp_2]):
        run_agent("create hello.py", tool_result_callback=result_cb)

    assert len(callbacks_received) == 1
    tool_name, res = callbacks_received[0]
    assert tool_name == "write_file"
    assert res["result"]["action"] == "created"
    assert "print('hello')" in res["result"]["content"]


def test_clean_agent_response_removes_json_and_xml():
    from zeus.core.agent import clean_agent_response

    raw_user_example = """{
"reasoning": "O usuário está perguntando por que o arquivo não foi criado. Vou verificar o estado atual do diretório e ver o que aconteceu com o comando anterior.",
  "response": null,
  "tool_calls": [
    {
      "name": "list_directory",
      "arguments": {
        "path": "."
      }
    }
  ]
</parameter>
</function>
</tool_call>"""

    cleaned = clean_agent_response(raw_user_example)
    assert cleaned == "O usuário está perguntando por que o arquivo não foi criado. Vou verificar o estado atual do diretório e ver o que aconteceu com o comando anterior."
    assert "tool_calls" not in cleaned
    assert "</parameter>" not in cleaned


def test_execute_tool_call_rejects_invalid_arguments():
    from unittest.mock import MagicMock

    from zeus.core.agent import execute_tool_call
    from zeus.core.registry import Tool

    spec = Tool(
        name="test_tool",
        description="A test tool",
        parameters={
            "type": "object",
            "properties": {"required_arg": {"type": "string"}},
            "required": ["required_arg"],
        },
        handler=lambda required_arg: {"ok": required_arg},
        tags=["test"],
    )
    with patch("zeus.core.agent.REGISTRY.get", return_value=spec):
        with patch("zeus.security.permissions.get_global_permission_manager") as mock_pm:
            mock_pm.return_value.is_tool_allowed.return_value = True
            with patch("zeus.security.guardrails.GuardrailsManager.validate_tool_call", return_value=None):
                result = execute_tool_call(
                    {"function": {"name": "test_tool", "arguments": {"wrong_arg": "x"}}},
                    MagicMock(),
                    MagicMock(),
                )
    assert "error" in result
    assert "missing required keys" in result["error"]


