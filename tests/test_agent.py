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
