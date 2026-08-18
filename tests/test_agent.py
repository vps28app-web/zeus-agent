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


