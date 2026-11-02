"""Anthropic model provider implementation."""

import os
from typing import Any, Dict, List

import requests

from zeus.providers.base import check_response_status, with_retries


def anthropic_chat(
    messages: List[Dict[str, str]],
    tools: List[Dict[str, Any]],
    model: str,
    stream: bool = False,
) -> Any:
    """Anthropic native provider via Messages API."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")

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

    def _call() -> Any:
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
        check_response_status(response, "Anthropic")
        return response

    response = with_retries(_call)
    if stream:
        return response
    return response.json()
