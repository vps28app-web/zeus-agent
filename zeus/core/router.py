"""Provider-agnostic model router."""

import json
import os
import time
from http.client import RemoteDisconnected
from typing import Any, Callable, Dict, List, Optional


def _with_retries(
    fn: Callable[[], Any],
    retries: int = 3,
    backoff: float = 1.0,
    exceptions: tuple = (ConnectionError,),
) -> Any:
    """Retry a callable with exponential backoff on transient network errors."""
    last_exc: Optional[Exception] = None
    for attempt in range(retries):
        try:
            return fn()
        except exceptions as exc:
            last_exc = exc
            if attempt < retries - 1:
                time.sleep(backoff * (2**attempt))
    raise last_exc  # type: ignore[misc]


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
    base_url = os.getenv("OPENCODE_GO_BASE_URL", "https://opencode.ai/zen/go/v1")
    if not api_key:
        raise RuntimeError("OPENCODE_GO_API_KEY not set")

    def _call() -> Any:
        response = requests.post(
            f"{base_url.rstrip('/')}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "x-opencode-session": "zeus-session",
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
        return response

    response = _with_retries(
        _call,
        retries=3,
        backoff=1.0,
        exceptions=(ConnectionError, RemoteDisconnected),
    )
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


def _sanitize_gemini_schema(schema: Any) -> Any:
    """Sanitize JSON Schema for Google Gemini API functionDeclarations.
    Gemini API strict schema validator rejects 'additionalProperties', '$ref', '$schema', 'title', 'default', 'examples', etc.
    It also strictly requires 'items' for array types and 'properties' for object types.
    """
    if not isinstance(schema, dict):
        return schema

    allowed_keys = {"type", "properties", "required", "description", "enum", "items", "format"}
    cleaned = {}

    for k, v in schema.items():
        if k not in allowed_keys:
            continue
        if k == "properties" and isinstance(v, dict):
            cleaned[k] = {prop_k: _sanitize_gemini_schema(prop_v) for prop_k, prop_v in v.items()}
        elif k == "items":
            if isinstance(v, dict):
                cleaned[k] = _sanitize_gemini_schema(v)
            elif isinstance(v, list) and v:
                cleaned[k] = _sanitize_gemini_schema(v[0])
            else:
                cleaned[k] = {"type": "string"}
        else:
            cleaned[k] = v

    if "type" not in cleaned:
        if "properties" in cleaned:
            cleaned["type"] = "object"
        elif "items" in cleaned:
            cleaned["type"] = "array"
        else:
            cleaned["type"] = "string"

    if cleaned.get("type") == "array" and "items" not in cleaned:
        cleaned["items"] = {"type": "string"}

    if cleaned.get("type") == "object" and "properties" not in cleaned:
        cleaned["properties"] = {}

    return cleaned



def _build_gemini_payload(
    messages: List[Dict[str, str]],
    tools: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Build the Gemini generateContent request payload."""
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
        fn_decls = []
        for t in tools:
            fn = t.get("function", {})
            fn_decl = {
                "name": fn.get("name", ""),
                "description": fn.get("description", "") or "No description provided.",
            }
            params = fn.get("parameters")
            if params:
                fn_decl["parameters"] = _sanitize_gemini_schema(params)
            fn_decls.append(fn_decl)
        payload["tools"] = [{"functionDeclarations": fn_decls}]
    return payload


def _send_gemini_request(
    model: str,
    payload: Dict[str, Any],
    api_key: Optional[str] = None,
    auth_header: Optional[str] = None,
) -> Dict[str, Any]:
    """Send a request to the Gemini Generative Language API."""
    import requests

    base_url = "https://generativelanguage.googleapis.com/v1beta/models"
    url = f"{base_url}/{model}:generateContent"
    if auth_header:
        headers = {"Authorization": auth_header, "Content-Type": "application/json"}
    elif api_key:
        url = f"{url}?key={api_key}"
        headers = {"Content-Type": "application/json"}
    else:
        raise RuntimeError("No API key or OAuth authorization available for Google Gemini.")

    response = requests.post(url, headers=headers, json=payload, timeout=120)
    if response.status_code != 200:
        try:
            err_data = response.json()
            err_msg = err_data.get("error", {}).get("message", response.text)
        except Exception:
            err_msg = response.text
        raise RuntimeError(f"Google Gemini API Error ({response.status_code}): {err_msg}")
    return response.json()


def google_api_chat(
    messages: List[Dict[str, str]],
    tools: List[Dict[str, Any]],
    model: str,
    stream: bool = False,
) -> Any:
    """Google Gemini via API key (GOOGLE_API_KEY or GEMINI_API_KEY)."""
    from pathlib import Path

    from dotenv import load_dotenv

    zeus_home = Path(os.getenv("ZEUS_HOME", os.path.expanduser("~/.zeus")))
    for path in [zeus_home / ".env", Path.cwd() / ".env"]:
        if path.exists():
            load_dotenv(path, override=False)

    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY ou GOOGLE_API_KEY nao configurada. "
            "Use o provider 'google_auth' para autenticacao via navegador."
        )

    payload = _build_gemini_payload(messages, tools)
    return _send_gemini_request(model, payload, api_key=api_key)


def google_auth_chat(
    messages: List[Dict[str, str]],
    tools: List[Dict[str, Any]],
    model: str,
    stream: bool = False,
) -> Any:
    """Google Gemini via OAuth 2.0 browser authentication."""
    from pathlib import Path

    from dotenv import load_dotenv

    zeus_home = Path(os.getenv("ZEUS_HOME", os.path.expanduser("~/.zeus")))
    for path in [zeus_home / ".env", Path.cwd() / ".env"]:
        if path.exists():
            load_dotenv(path, override=False)

    try:
        from zeus.core.google_oauth_desktop import get_access_token
    except Exception as exc:  # pragma: no cover - import guard
        raise RuntimeError(f"Falha ao carregar modulo OAuth: {exc}") from exc

    access_token = get_access_token()
    if not access_token:
        raise RuntimeError(
            "Token OAuth do Google nao disponivel. Execute '/auth google' no CLI."
        )

    payload = _build_gemini_payload(messages, tools)
    try:
        return _send_gemini_request(model, payload, auth_header=f"Bearer {access_token}")
    except RuntimeError as exc:
        err_msg = str(exc)
        if "401" in err_msg:
            access_token = get_access_token(force_new=True)
            return _send_gemini_request(model, payload, auth_header=f"Bearer {access_token}")
        raise



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
    "google": google_api_chat,
    "google_api": google_api_chat,
    "google_auth": google_auth_chat,
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

    try:
        response = PROVIDERS[provider](messages, tools, model, stream=stream)
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
