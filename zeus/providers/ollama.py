"""Ollama local model provider implementation."""

import os
from typing import Any, Dict, List

import requests

from zeus.providers.base import check_response_status, with_retries


def ollama_chat(
    messages: List[Dict[str, str]],
    tools: List[Dict[str, Any]],
    model: str,
    stream: bool = False,
) -> Any:
    """Call Ollama local server."""
    host = os.getenv("OLLAMA_HOST", "http://localhost:11434")

    def _call() -> Any:
        response = requests.post(
            f"{host.rstrip('/')}/api/chat",
            json={
                "model": model,
                "messages": messages,
                "stream": stream,
                "tools": tools,
            },
            timeout=120,
            stream=stream,
        )
        check_response_status(response, "Ollama")
        return response

    response = with_retries(_call)
    if stream:
        return response
    return response.json()
