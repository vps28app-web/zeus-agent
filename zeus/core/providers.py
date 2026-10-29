"""Connection metadata for additional OpenAI-compatible model providers."""

OPENAI_COMPATIBLE_PROVIDERS = {
    "groq": {
        "api_key_env": "GROQ_API_KEY",
        "base_url": "https://api.groq.com/openai/v1",
        "list_models": True,
    },
    "xai": {
        "api_key_env": "XAI_API_KEY",
        "base_url": "https://api.x.ai/v1",
        "list_models": True,
    },
    "together": {
        "api_key_env": "TOGETHER_API_KEY",
        "base_url": "https://api.together.ai/v1",
        "list_models": True,
    },
    "fireworks": {
        "api_key_env": "FIREWORKS_API_KEY",
        "base_url": "https://api.fireworks.ai/inference/v1",
        "list_models": False,
    },
    "cohere": {
        "api_key_env": "COHERE_API_KEY",
        "base_url": "https://api.cohere.ai/compatibility/v1",
        "list_models": False,
    },
}
