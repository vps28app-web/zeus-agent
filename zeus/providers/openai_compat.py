"""OpenAI and OpenAI-compatible model providers."""

import os
from typing import Any, Dict, List

import requests

from zeus.core.providers import OPENAI_COMPATIBLE_PROVIDERS
from zeus.providers.base import check_response_status, with_retries


def openrouter_chat(
    messages: List[Dict[str, str]],
    tools: List[Dict[str, Any]],
    model: str,
    stream: bool = False,
) -> Any:
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY not set")

    def _call() -> Any:
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
        check_response_status(response, "OpenRouter")
        return response

    response = with_retries(_call)
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
                "User-Agent": "ZeusAgent/0.1.0",
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
        check_response_status(response, "OpenCode Go")
        return response

    response = with_retries(_call)
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
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set")

    def _call() -> Any:
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
        check_response_status(response, "OpenAI")
        return response

    response = with_retries(_call)
    if stream:
        return response
    return response.json()


def deepseek_chat(
    messages: List[Dict[str, str]],
    tools: List[Dict[str, Any]],
    model: str,
    stream: bool = False,
) -> Any:
    """DeepSeek native provider (OpenAI-compatible)."""
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY not set")

    def _call() -> Any:
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
        check_response_status(response, "DeepSeek")
        return response

    response = with_retries(_call)
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
    api_key = os.getenv("MISTRAL_API_KEY")
    if not api_key:
        raise RuntimeError("MISTRAL_API_KEY not set")

    def _call() -> Any:
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
        check_response_status(response, "Mistral")
        return response

    response = with_retries(_call)
    if stream:
        return response
    return response.json()


def openai_compatible_chat(
    provider: str,
    messages: List[Dict[str, str]],
    tools: List[Dict[str, Any]],
    model: str,
    stream: bool = False,
) -> Any:
    """Call a provider that implements the OpenAI Chat Completions contract."""
    config = OPENAI_COMPATIBLE_PROVIDERS[provider]
    api_key_name = config["api_key_env"]
    api_key = os.getenv(api_key_name)
    if not api_key:
        raise RuntimeError(f"{api_key_name} not set")

    def _call() -> Any:
        response = requests.post(
            f"{config['base_url'].rstrip('/')}/chat/completions",
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
        check_response_status(response, provider.capitalize())
        return response

    response = with_retries(_call)
    if stream:
        return response
    return response.json()


def groq_chat(messages, tools, model, stream=False):
    return openai_compatible_chat("groq", messages, tools, model, stream)


def xai_chat(messages, tools, model, stream=False):
    return openai_compatible_chat("xai", messages, tools, model, stream)


def together_chat(messages, tools, model, stream=False):
    return openai_compatible_chat("together", messages, tools, model, stream)


def fireworks_chat(messages, tools, model, stream=False):
    return openai_compatible_chat("fireworks", messages, tools, model, stream)


def cohere_chat(messages, tools, model, stream=False):
    return openai_compatible_chat("cohere", messages, tools, model, stream)
