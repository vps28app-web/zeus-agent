"""Provider-agnostic model router."""

import json
import os
from typing import Any, Dict, List, Optional


def openrouter_chat(
    messages: List[Dict[str, str]],
    tools: List[Dict[str, Any]],
    model: str,
    stream: bool = False,
) -> Any:
    import requests

    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY not set")

    response = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": messages,
            "tools": tools,
            "stream": stream,
        },
        timeout=120,
        stream=stream,
    )
    response.raise_for_status()
    if stream:
        return response
    return response.json()


def ollama_chat(
    messages: List[Dict[str, str]],
    tools: List[Dict[str, Any]],
    model: str,
    stream: bool = False,
) -> Any:
    import requests

    response = requests.post(
        os.getenv("OLLAMA_HOST", "http://localhost:11434") + "/api/chat",
        json={
            "model": model,
            "messages": messages,
            "stream": stream,
            "tools": tools,
        },
        timeout=120,
        stream=stream,
    )
    response.raise_for_status()
    if stream:
        return response
    return response.json()


def opencode_go_chat(
    messages: List[Dict[str, str]],
    tools: List[Dict[str, Any]],
    model: str,
    stream: bool = False,
) -> Any:
    """OpenCode Go provider via OpenAI-compatible endpoint."""
    import requests

    api_key = os.getenv("OPENCODE_GO_API_KEY")
    base_url = os.getenv("OPENCODE_GO_BASE_URL", "https://api.opencode.co/v1")
    if not api_key:
        raise RuntimeError("OPENCODE_GO_API_KEY not set")

    response = requests.post(
        f"{base_url.rstrip('/')}/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": messages,
            "tools": tools,
            "stream": stream,
        },
        timeout=120,
        stream=stream,
    )
    response.raise_for_status()
    if stream:
        return response
    return response.json()


def openai_chat(
    messages: List[Dict[str, str]],
    tools: List[Dict[str, Any]],
    model: str,
    stream: bool = False,
) -> Any:
    """OpenAI native provider."""
    import requests

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set")

    response = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": messages,
            "tools": tools if tools else None,
            "stream": stream,
        },
        timeout=120,
        stream=stream,
    )
    response.raise_for_status()
    if stream:
        return response
    return response.json()


def anthropic_chat(
    messages: List[Dict[str, str]],
    tools: List[Dict[str, Any]],
    model: str,
    stream: bool = False,
) -> Any:
    """Anthropic native provider via Messages API."""
    import requests

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")

    # Anthropic uses "user" and "assistant" roles, same as OpenAI.
    # It requires max_tokens.
    system_message = ""
    chat_messages = []
    for m in messages:
        if m.get("role") == "system":
            system_message += m.get("content", "") + "\n"
        else:
            chat_messages.append(m)

    payload: Dict[str, Any] = {
        "model": model,
        "messages": chat_messages,
        "max_tokens": 4096,
        "stream": stream,
    }
    if system_message:
        payload["system"] = system_message.strip()
    if tools:
        payload["tools"] = tools

    response = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": api_key,
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
        },
        json=payload,
        timeout=120,
        stream=stream,
    )
    response.raise_for_status()
    if stream:
        return response
    return response.json()


def google_chat(
    messages: List[Dict[str, str]],
    tools: List[Dict[str, Any]],
    model: str,
    stream: bool = False,
) -> Any:
    """Google Gemini native provider via Generative Language API."""
    import requests

    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY not set")

    # Gemini uses contents format with roles mapped to "user" and "model".
    contents = []
    system_parts = []
    for m in messages:
        role = m.get("role")
        content = m.get("content", "")
        if role == "system":
            system_parts.append({"text": content})
        elif role == "assistant":
            contents.append({"role": "model", "parts": [{"text": content}]})
        else:
            contents.append({"role": "user", "parts": [{"text": content}]})

    payload: Dict[str, Any] = {"contents": contents}
    if system_parts:
        payload["systemInstruction"] = {"parts": system_parts}
    if tools:
        payload["tools"] = [{"functionDeclarations": [t["function"] for t in tools]}]

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        f"?key={api_key}"
    )
    response = requests.post(
        url,
        headers={"Content-Type": "application/json"},
        json=payload,
        timeout=120,
    )
    response.raise_for_status()
    return response.json()


def deepseek_chat(
    messages: List[Dict[str, str]],
    tools: List[Dict[str, Any]],
    model: str,
    stream: bool = False,
) -> Any:
    """DeepSeek native provider (OpenAI-compatible)."""
    import requests

    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY not set")

    response = requests.post(
        "https://api.deepseek.com/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": messages,
            "tools": tools if tools else None,
            "stream": stream,
        },
        timeout=120,
        stream=stream,
    )
    response.raise_for_status()
    if stream:
        return response
    return response.json()


def mistral_chat(
    messages: List[Dict[str, str]],
    tools: List[Dict[str, Any]],
    model: str,
    stream: bool = False,
) -> Any:
    """Mistral native provider (OpenAI-compatible)."""
    import requests

    api_key = os.getenv("MISTRAL_API_KEY")
    if not api_key:
        raise RuntimeError("MISTRAL_API_KEY not set")

    response = requests.post(
        "https://api.mistral.ai/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": messages,
            "tools": tools if tools else None,
            "stream": stream,
        },
        timeout=120,
        stream=stream,
    )
    response.raise_for_status()
    if stream:
        return response
    return response.json()


PROVIDERS = {
    "openrouter": openrouter_chat,
    "ollama": ollama_chat,
    "opencode_go": opencode_go_chat,
    "openai": openai_chat,
    "anthropic": anthropic_chat,
    "google": google_chat,
    "deepseek": deepseek_chat,
    "mistral": mistral_chat,
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

    response = PROVIDERS[provider](messages, tools, model, stream=stream)

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

    if provider == "google":
        candidates = response.get("candidates", [])
        if not candidates:
            return {"choices": [{"message": {"role": "assistant", "content": None}}]}
        parts = candidates[0].get("content", {}).get("parts", [])
        text_parts = []
        tool_calls = []
        for part in parts:
            if "text" in part:
                text_parts.append(part["text"])
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
    """Parse streaming response and accumulate into a normalized dict."""

    content_parts = []
    tool_calls: Dict[int, Dict[str, Any]] = {}

    for line in response.iter_lines():
        if not line:
            continue
        decoded = line.decode("utf-8")
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
