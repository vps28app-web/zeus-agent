"""Unit tests for zeus/core/router.py."""

import json
import os
from unittest.mock import MagicMock, patch

import pytest

from zeus.core import router


def test_providers_dict_is_populated():
    assert "openrouter" in router.PROVIDERS
    assert "ollama" in router.PROVIDERS
    assert "opencode_go" in router.PROVIDERS
    assert "openai" in router.PROVIDERS
    assert "anthropic" in router.PROVIDERS
    assert "google" in router.PROVIDERS
    assert "deepseek" in router.PROVIDERS
    assert "mistral" in router.PROVIDERS


def test_chat_unknown_provider():
    with pytest.raises(ValueError, match="Unknown provider"):
        router.chat([], [], provider="invalid_provider")


@patch("zeus.core.router.openrouter_chat")
def test_chat_uses_env_provider_and_model(mock_chat):
    mock_chat.return_value = {
        "choices": [{"message": {"role": "assistant", "content": "hi"}}]
    }
    env = {
        "ZEUS_PROVIDER": "openrouter",
        "ZEUS_MODEL": "openrouter/auto",
        "OPENROUTER_API_KEY": "fake",
    }
    with patch.dict(os.environ, env, clear=False):
        with patch("zeus.core.router.PROVIDERS", {"openrouter": mock_chat}):
            response = router.chat([{"role": "user", "content": "hello"}], [])
    assert response["choices"][0]["message"]["content"] == "hi"
    mock_chat.assert_called_once()


@patch("zeus.core.router.openai_chat")
def test_chat_passes_provider_and_model(mock_chat):
    mock_chat.return_value = {
        "choices": [{"message": {"role": "assistant", "content": "ok"}}]
    }
    with patch.dict(os.environ, {"OPENAI_API_KEY": "fake"}, clear=False):
        with patch("zeus.core.router.PROVIDERS", {"openai": mock_chat}):
            response = router.chat(
                [{"role": "user", "content": "hello"}],
                [],
                provider="openai",
                model="gpt-4o",
            )
    assert response["choices"][0]["message"]["content"] == "ok"
    mock_chat.assert_called_once()


def test_normalize_ollama_response():
    raw = {
        "message": {"role": "assistant", "content": "hello"},
        "prompt_eval_count": 10,
        "eval_count": 5,
    }
    normalized = router._normalize_response(raw, "ollama")
    assert normalized["choices"][0]["message"]["content"] == "hello"
    assert normalized["usage"]["prompt_tokens"] == 10
    assert normalized["usage"]["completion_tokens"] == 5


def test_normalize_anthropic_response_text_only():
    raw = {
        "content": [
            {"type": "text", "text": "hello"},
            {"type": "text", "text": "world"},
        ],
        "usage": {"input_tokens": 7, "output_tokens": 2},
    }
    normalized = router._normalize_response(raw, "anthropic")
    message = normalized["choices"][0]["message"]
    assert message["content"] == "hello\nworld"
    assert message["tool_calls"] is None
    assert normalized["usage"]["prompt_tokens"] == 7
    assert normalized["usage"]["completion_tokens"] == 2


def test_normalize_anthropic_response_with_tool_use():
    raw = {
        "content": [
            {"type": "tool_use", "id": "tu_1", "name": "run_terminal", "input": {"command": "ls"}},
        ],
    }
    normalized = router._normalize_response(raw, "anthropic")
    message = normalized["choices"][0]["message"]
    assert message["tool_calls"] is not None
    assert message["tool_calls"][0]["function"]["name"] == "run_terminal"
    assert json.loads(message["tool_calls"][0]["function"]["arguments"]) == {"command": "ls"}


def test_normalize_google_response_text_only():
    raw = {
        "candidates": [
            {
                "content": {
                    "parts": [{"text": "hello from gemini"}]
                }
            }
        ],
        "usageMetadata": {"promptTokenCount": 4, "candidatesTokenCount": 3},
    }
    normalized = router._normalize_response(raw, "google")
    message = normalized["choices"][0]["message"]
    assert message["content"] == "hello from gemini"
    assert normalized["usage"]["prompt_tokens"] == 4
    assert normalized["usage"]["completion_tokens"] == 3


def test_normalize_google_response_function_call():
    raw = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {"functionCall": {"name": "read_file", "args": {"path": "/tmp/test.txt"}}}
                    ]
                }
            }
        ],
    }
    normalized = router._normalize_response(raw, "google")
    message = normalized["choices"][0]["message"]
    assert message["tool_calls"] is not None
    assert message["tool_calls"][0]["function"]["name"] == "read_file"
    assert json.loads(message["tool_calls"][0]["function"]["arguments"]) == {"path": "/tmp/test.txt"}


def test_normalize_google_empty_candidates():
    normalized = router._normalize_response({"candidates": []}, "google")
    assert normalized["choices"][0]["message"]["content"] is None


def test_sanitize_gemini_schema_removes_disallowed_keys():
    schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "A name", "title": "Name"},
        },
        "required": ["name"],
        "additionalProperties": False,
        "$schema": "http://json-schema.org/draft-07/schema#",
    }
    cleaned = router._sanitize_gemini_schema(schema)
    assert cleaned["type"] == "object"
    assert "additionalProperties" not in cleaned
    assert "$schema" not in cleaned
    assert "title" not in cleaned["properties"]["name"]
    assert cleaned["properties"]["name"]["type"] == "string"


def test_sanitize_gemini_schema_adds_items_for_array():
    schema = {"type": "array"}
    cleaned = router._sanitize_gemini_schema(schema)
    assert cleaned["type"] == "array"
    assert "items" in cleaned
    assert cleaned["items"]["type"] == "string"


@patch("requests.post")
def test_google_chat_loads_dotenv_and_calls_api(mock_post):
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = {
        "candidates": [{"content": {"parts": [{"text": "ok"}]}}]
    }
    with patch.dict(os.environ, {"GOOGLE_API_KEY": "fake-google-key"}, clear=False):
        response = router.google_chat(
            [{"role": "user", "content": "hello"}],
            [],
            "gemini-1.5-flash",
        )
    assert response["candidates"][0]["content"]["parts"][0]["text"] == "ok"
    mock_post.assert_called_once()


def test_google_chat_missing_api_key():
    with patch.dict(os.environ, {"GOOGLE_API_KEY": "", "GEMINI_API_KEY": ""}, clear=False):
        with pytest.raises(RuntimeError, match="GOOGLE_API_KEY or GEMINI_API_KEY not set"):
            router.google_chat([], [], "gemini-1.5-flash")


@patch("requests.post")
def test_openai_chat_missing_key_raises(mock_post):
    mock_post.side_effect = RuntimeError("OPENAI_API_KEY not set")
    with patch.dict(os.environ, {"OPENAI_API_KEY": ""}, clear=False):
        with pytest.raises(RuntimeError):
            router.openai_chat([], [], "gpt-4o")


def test_stream_response_accumulates_content():
    lines = [
        b'data: {"choices": [{"delta": {"content": "hello"}}]}',
        b'data: {"choices": [{"delta": {"content": " world"}}]}',
        b'data: [DONE]',
    ]
    mock_response = MagicMock()
    mock_response.iter_lines.return_value = lines
    result = router._stream_response(mock_response, "openai")
    assert result["choices"][0]["message"]["content"] == "hello world"


def test_stream_response_accumulates_tool_calls():
    lines = [
        b'data: {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"name": "read"}}]}}]}',
        b'data: {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": "{\\"path\\": \\"/tmp\\"}"}}]}}]}',
        b'data: [DONE]',
    ]
    mock_response = MagicMock()
    mock_response.iter_lines.return_value = lines
    result = router._stream_response(mock_response, "openai")
    tool_calls = result["choices"][0]["message"]["tool_calls"]
    assert tool_calls is not None
    assert tool_calls[0]["function"]["name"] == "read"
    assert tool_calls[0]["function"]["arguments"] == '{"path": "/tmp"}'
