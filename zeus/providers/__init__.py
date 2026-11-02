"""Zeus Model Providers package."""

from zeus.providers.anthropic import anthropic_chat
from zeus.providers.base import (
    DEFAULT_RETRY_EXCEPTIONS,
    TransientServerError,
    check_response_status,
    with_retries,
)
from zeus.providers.gemini import (
    build_gemini_payload,
    google_api_chat,
    google_auth_chat,
    sanitize_gemini_schema,
    send_gemini_request,
)
from zeus.providers.ollama import ollama_chat
from zeus.providers.openai_compat import (
    cohere_chat,
    deepseek_chat,
    fireworks_chat,
    groq_chat,
    mistral_chat,
    openai_chat,
    openai_compatible_chat,
    opencode_go_chat,
    openrouter_chat,
    together_chat,
    xai_chat,
)

__all__ = [
    "TransientServerError",
    "DEFAULT_RETRY_EXCEPTIONS",
    "with_retries",
    "check_response_status",
    "anthropic_chat",
    "google_api_chat",
    "google_auth_chat",
    "sanitize_gemini_schema",
    "build_gemini_payload",
    "send_gemini_request",
    "ollama_chat",
    "openrouter_chat",
    "opencode_go_chat",
    "openai_chat",
    "deepseek_chat",
    "mistral_chat",
    "openai_compatible_chat",
    "groq_chat",
    "xai_chat",
    "together_chat",
    "fireworks_chat",
    "cohere_chat",
]
