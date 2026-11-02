"""Provider-agnostic model router."""

import json
import os
import time
from http.client import RemoteDisconnected
from typing import Any, Callable, Dict, List, Optional

import requests

from zeus.core.providers import OPENAI_COMPATIBLE_PROVIDERS
from zeus.providers import (
    DEFAULT_RETRY_EXCEPTIONS,
    TransientServerError,
    anthropic_chat,
    build_gemini_payload,
    check_response_status,
    cohere_chat,
    deepseek_chat,
    fireworks_chat,
    google_api_chat,
    google_auth_chat,
    groq_chat,
    mistral_chat,
    ollama_chat,
    openai_chat,
    openai_compatible_chat,
    opencode_go_chat,
    openrouter_chat,
    sanitize_gemini_schema,
    send_gemini_request,
    together_chat,
    with_retries,
    xai_chat,
)

# Backward-compatibility aliases for existing imports and test mocking
_with_retries = with_retries
_check_response_status = check_response_status
_sanitize_gemini_schema = sanitize_gemini_schema
_build_gemini_payload = build_gemini_payload
_send_gemini_request = send_gemini_request

PROVIDERS = {
    "openrouter": openrouter_chat,
    "ollama": ollama_chat,
    "opencode_go": opencode_go_chat,
    "openai": openai_chat,
    "anthropic": anthropic_chat,
    "google": google_api_chat,
    "google_api": google_api_chat,
    "google_auth": google_auth_chat,
    "deepseek": deepseek_chat,
    "mistral": mistral_chat,
    "groq": groq_chat,
    "xai": xai_chat,
    "together": together_chat,
    "fireworks": fireworks_chat,
    "cohere": cohere_chat,
}


def chat(
    messages: List[Dict[str, str]],
    tools: List[Dict[str, Any]],
    provider: Optional[str] = None,
    model: Optional[str] = None,
    stream: bool = False,
    stream_callback=None,
) -> Dict[str, Any]:
    provider = provider or os.getenv("ZEUS_PROVIDER", "openrouter")
    model = model or os.getenv("ZEUS_MODEL", "openrouter/auto")

    if provider not in PROVIDERS:
        raise ValueError(f"Unknown provider: {provider}. Available: {list(PROVIDERS)}")

    try:
        response = PROVIDERS[provider](messages, tools, model, stream=stream)
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout, RemoteDisconnected) as e:
        raise RuntimeError(
            f"Falha de conexão com o provedor '{provider}': verifique sua internet / "
            f"connection failed (check internet). Detalhe: {type(e).__name__}"
        ) from e
    except RuntimeError as e:
        err = str(e).lower()
        if "api_key" in err or "api key" in err:
            key_name = {
                "openrouter": "OPENROUTER_API_KEY",
                "opencode_go": "OPENCODE_GO_API_KEY",
                "openai": "OPENAI_API_KEY",
                "anthropic": "ANTHROPIC_API_KEY",
                "google": "GEMINI_API_KEY / GOOGLE_API_KEY",
                "google_api": "GEMINI_API_KEY / GOOGLE_API_KEY",
                "google_auth": "OAuth via /auth google",
                "deepseek": "DEEPSEEK_API_KEY",
                "mistral": "MISTRAL_API_KEY",
                "groq": "GROQ_API_KEY",
                "xai": "XAI_API_KEY",
                "together": "TOGETHER_API_KEY",
                "fireworks": "FIREWORKS_API_KEY",
                "cohere": "COHERE_API_KEY",
            }.get(provider, f"chave de API do provider '{provider}'")
            raise RuntimeError(
                f"Chave de API não configurada para o provider '{provider}'. "
                f"Defina {key_name} no arquivo .env ou via /config set {key_name.split()[0]} <valor>."
            ) from e
        raise

    if stream:
        return _stream_response(response, provider, stream_callback)

    # Normalize provider-specific responses to OpenAI-like format
    return _normalize_response(response, provider)


def _normalize_response(response: Dict[str, Any], provider: str) -> Dict[str, Any]:
    """Convert provider-native response to OpenAI-like choices/message format."""
    if provider == "ollama":
        message = response.get("message", {})
        res = {
            "choices": [
                {
                    "message": {
                        "role": message.get("role", "assistant"),
                        "content": message.get("content"),
                        "tool_calls": message.get("tool_calls"),
                    }
                }
            ]
        }
        if "prompt_eval_count" in response or "eval_count" in response:
            res["usage"] = {
                "prompt_tokens": response.get("prompt_eval_count", 0),
                "completion_tokens": response.get("eval_count", 0),
            }
        return res

    if provider == "anthropic":
        content_blocks = response.get("content", [])
        text_parts = []
        tool_calls = []
        for block in content_blocks:
            if block.get("type") == "text":
                text_parts.append(block.get("text", ""))
            elif block.get("type") == "tool_use":
                tool_calls.append({
                    "id": block.get("id", ""),
                    "type": "function",
                    "function": {
                        "name": block.get("name", ""),
                        "arguments": json.dumps(block.get("input", {})),
                    },
                })
        res = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "\n".join(text_parts) if text_parts else None,
                        "tool_calls": tool_calls if tool_calls else None,
                    }
                }
            ]
        }
        if "usage" in response:
            res["usage"] = {
                "prompt_tokens": response["usage"].get("input_tokens", 0),
                "completion_tokens": response["usage"].get("output_tokens", 0),
            }
        return res

    if provider == "google" or provider.startswith("google_"):
        candidates = response.get("candidates", [])
        if not candidates:
            return {"choices": [{"message": {"role": "assistant", "content": None}}]}
        parts = candidates[0].get("content", {}).get("parts", [])
        text_parts = []
        tool_calls = []
        for part in parts:
            if "text" in part:
                txt = part["text"]
                parsed_tools = False
                try:
                    data = json.loads(txt.strip())
                    if isinstance(data, dict) and "tool_calls" in data:
                        for tc in data["tool_calls"]:
                            t_name = tc.get("name") or (tc.get("function", {}).get("name") if isinstance(tc.get("function"), dict) else None)
                            t_args = tc.get("arguments") or tc.get("inputs") or (tc.get("function", {}).get("arguments") if isinstance(tc.get("function"), dict) else {})
                            if isinstance(t_args, dict):
                                t_args_str = json.dumps(t_args)
                            else:
                                t_args_str = str(t_args)
                            if t_name:
                                tool_calls.append({
                                    "id": t_name,
                                    "type": "function",
                                    "function": {
                                        "name": t_name,
                                        "arguments": t_args_str,
                                    },
                                })
                        parsed_tools = True
                        if data.get("response"):
                            text_parts.append(str(data["response"]))
                except Exception:
                    pass
                if not parsed_tools:
                    text_parts.append(txt)
            elif "functionCall" in part:
                fc = part["functionCall"]
                tool_calls.append({
                    "id": fc.get("name", ""),
                    "type": "function",
                    "function": {
                        "name": fc.get("name", ""),
                        "arguments": json.dumps(fc.get("args", {})),
                    },
                })

        res = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "\n".join(text_parts) if text_parts else None,
                        "tool_calls": tool_calls if tool_calls else None,
                    }
                }
            ]
        }
        usage_meta = response.get("usageMetadata", {})
        if usage_meta:
            res["usage"] = {
                "prompt_tokens": usage_meta.get("promptTokenCount", 0),
                "completion_tokens": usage_meta.get("candidatesTokenCount", 0),
            }
        return res

    # openrouter, openai, opencode_go, deepseek, mistral already return OpenAI-like format
    return response


def _stream_response(response, provider: str, callback=None) -> Dict[str, Any]:
    """Parse streaming response and accumulate into a normalized dict.

    Handles SSE (OpenAI/OpenRouter), NDJSON (Ollama), and Anthropic SSE formats.
    """

    content_parts = []
    tool_calls: Dict[int, Dict[str, Any]] = {}

    for line in response.iter_lines():
        if not line:
            continue
        decoded = line.decode("utf-8")

        # Ollama returns NDJSON lines like {"message": {"role": "assistant", "content": "..."}}
        if provider == "ollama":
            try:
                chunk = json.loads(decoded)
            except json.JSONDecodeError:
                continue
            if chunk.get("done"):
                break
            delta_content = chunk.get("message", {}).get("content")
            if delta_content:
                content_parts.append(delta_content)
                if callback:
                    callback(delta_content)
            # Ollama tool calls are delivered inline in non-streaming mode; skip here.
            continue

        if decoded.startswith("data: "):
            decoded = decoded[6:]
        if decoded.strip() == "[DONE]":
            break
        try:
            chunk = json.loads(decoded)
        except json.JSONDecodeError:
            continue

        if provider == "anthropic":
            delta = chunk.get("delta", {})
            delta_content = delta.get("text")
            if delta_content:
                content_parts.append(delta_content)
                if callback:
                    callback(delta_content)
            # Anthropic tool_use deltas are trickier; skipping streaming tool parsing.
            continue

        delta = chunk.get("choices", [{}])[0].get("delta", {})
        delta_content = delta.get("content")
        if delta_content:
            content_parts.append(delta_content)
            if callback:
                callback(delta_content)

        delta_tool_calls = delta.get("tool_calls") or []
        for tc in delta_tool_calls:
            idx = tc.get("index", 0)
            if idx not in tool_calls:
                tool_calls[idx] = {"id": "", "function": {"name": "", "arguments": ""}}
            if tc.get("id"):
                tool_calls[idx]["id"] += tc["id"]
            fn = tc.get("function", {})
            if fn.get("name"):
                tool_calls[idx]["function"]["name"] += fn["name"]
            if fn.get("arguments"):
                tool_calls[idx]["function"]["arguments"] += fn["arguments"]

    final_content = "".join(content_parts) if content_parts else None
    final_tool_calls = list(tool_calls.values()) if tool_calls else None

    return {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": final_content,
                    "tool_calls": final_tool_calls,
                }
            }
        ]
    }
