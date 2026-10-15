"""Configuration management tools for Zeus framework."""

import os
from pathlib import Path
from typing import Any, Dict, Optional

from zeus.config.settings import config_path, load_config, save_config
from zeus.core.registry import register_tool


def _get_env_path() -> Path:
    zeus_home = Path(os.getenv("ZEUS_HOME", os.path.expanduser("~/.zeus")))
    zeus_home.mkdir(parents=True, exist_ok=True)
    return zeus_home / ".env"


def _upsert_env(key: str, value: str) -> None:
    path = _get_env_path()
    content = path.read_text(encoding="utf-8") if path.exists() else ""
    lines = content.splitlines(keepends=True)
    if lines and not lines[-1].endswith("\n"):
        lines[-1] += "\n"

    updated = False
    for i, line in enumerate(lines):
        if line.strip().startswith(f"{key}=") or line.strip().startswith(f"#{key}="):
            lines[i] = f"{key}={value}\n"
            updated = True
            break

    if not updated:
        lines.append(f"{key}={value}\n")

    path.write_text("".join(lines), encoding="utf-8")
    if os.name != "nt":
        path.chmod(0o600)

    # Update in memory; keep GEMINI and GOOGLE aliases in sync for router compatibility.
    os.environ[key] = value
    if key == "GEMINI_API_KEY":
        os.environ["GOOGLE_API_KEY"] = value
    elif key == "GOOGLE_API_KEY":
        os.environ["GEMINI_API_KEY"] = value


def _is_config_yaml_key(key: str) -> bool:
    """Keys that belong to config.yaml instead of .env."""
    return key.lower() in {"max_turns"}


def _update_config_yaml(key: str, value: str) -> Dict[str, Any]:
    config = load_config()
    config_key = key.lower()
    if config_key == "max_turns":
        try:
            config["max_turns"] = int(value)
        except ValueError:
            return {"error": f"Valor inválido para max_turns: {value!r}. Deve ser um inteiro."}
    else:
        config[config_key] = value
    save_config(config)
    return {"status": "success", "key": config_key, "value": str(config[config_key])}


def get_zeus_config() -> Dict[str, Any]:
    """Retrieve the current Zeus LLM provider, model, and API keys status."""
    keys_to_check = [
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "GOOGLE_OAUTH_CLIENT_ID",
        "GOOGLE_OAUTH_CLIENT_SECRET",
        "OPENROUTER_API_KEY",
        "OPENCODE_GO_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "DEEPSEEK_API_KEY",
        "TELEGRAM_BOT_TOKEN",
    ]
    status = {}
    for k in keys_to_check:
        val = os.getenv(k)
        if val:
            status[k] = f"Configurado (***{val[-4:] if len(val) >= 4 else '***'})"
        else:
            status[k] = "Não configurado"

    return {
        "zeus_provider": os.getenv("ZEUS_PROVIDER", "openrouter"),
        "zeus_model": os.getenv("ZEUS_MODEL", "openrouter/auto"),
        "max_turns": load_config().get("max_turns", 20),
        "api_keys_status": status,
        "config_file": str(config_path()),
        "env_file": str(_get_env_path()),
    }


def update_zeus_config(key: str, value: str) -> Dict[str, Any]:
    """Update a configuration key or API key in Zeus settings (.env or config.yaml)."""
    key_clean = key.strip().upper()
    val_clean = value.strip()
    if not key_clean:
        return {"error": "Key name cannot be empty"}

    if _is_config_yaml_key(key_clean):
        result = _update_config_yaml(key_clean, val_clean)
        if "error" in result:
            return result
        return {
            "status": "success",
            "message": f"Configuração '{key_clean}' atualizada em {config_path()}.",
            "key": result["key"],
            "new_value_masked": str(result["value"]),
        }

    _upsert_env(key_clean, val_clean)
    return {
        "status": "success",
        "message": f"Configuração '{key_clean}' atualizada com sucesso.",
        "key": key_clean,
        "new_value_masked": f"***{val_clean[-4:]}" if len(val_clean) >= 4 else "***",
    }


def list_available_models(provider: Optional[str] = None) -> Dict[str, Any]:
    """List available LLM providers and recommended models."""
    from zeus.cli.setup_commands import MODEL_PRESETS

    if provider:
        prov_lower = provider.lower()
        if prov_lower in MODEL_PRESETS:
            models = fetch_models(prov_lower)
            if "error" not in models and models.get("models"):
                return models
            # Fallback to static presets if API listing fails or returns empty
            return {
                "provider": prov_lower,
                "models": [m[0] for m in MODEL_PRESETS[prov_lower]],
                "details": MODEL_PRESETS[prov_lower],
                "warning": models.get("error") if "error" in models else "API retornou lista vazia",
            }
        return {"error": f"Provider '{provider}' n\u00e3o encontrado.", "available_providers": list(MODEL_PRESETS.keys())}

    return {
        "providers": list(MODEL_PRESETS.keys()),
        "presets": MODEL_PRESETS,
    }


def fetch_models(provider: str) -> Dict[str, Any]:
    """Fetch available models from a provider's API.

    Falls back to returning an error dict if the request fails or the provider
    does not expose a public model listing endpoint.
    """
    import requests

    provider = provider.lower()

    if provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return {"error": "OPENAI_API_KEY n\u00e3o configurada."}
        try:
            response = requests.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
            models = sorted(m.get("id", "") for m in data.get("data", []) if m.get("id"))
            return {"provider": provider, "models": models}
        except Exception as exc:
            return {"error": f"Falha ao listar modelos OpenAI: {exc}"}

    if provider == "openrouter":
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            return {"error": "OPENROUTER_API_KEY n\u00e3o configurada."}
        try:
            response = requests.get(
                "https://openrouter.ai/api/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
            models = sorted(m.get("id", "") for m in data.get("data", []) if m.get("id"))
            return {"provider": provider, "models": models}
        except Exception as exc:
            return {"error": f"Falha ao listar modelos OpenRouter: {exc}"}

    if provider == "anthropic":
        # Anthropic does not expose a public models endpoint; use static presets.
        from zeus.cli.setup_commands import MODEL_PRESETS

        return {
            "provider": provider,
            "models": [m[0] for m in MODEL_PRESETS.get(provider, [])],
            "details": MODEL_PRESETS.get(provider, []),
        }

    if provider in ("google", "google_api"):
        api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        if not api_key:
            return {"error": "GEMINI_API_KEY ou GOOGLE_API_KEY nao configurada."}
        try:
            response = requests.get(
                "https://generativelanguage.googleapis.com/v1beta/models",
                params={"key": api_key},
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
            models = sorted(m.get("name", "").replace("models/", "") for m in data.get("models", []) if m.get("name"))
            return {"provider": provider, "models": models}
        except Exception as exc:
            return {"error": f"Falha ao listar modelos Google: {exc}"}

    if provider == "google_auth":
        try:
            from zeus.core.google_oauth_desktop import get_access_token
        except Exception as exc:
            return {"error": f"Falha ao carregar modulo OAuth: {exc}"}
        access_token = get_access_token()
        if not access_token:
            return {"error": "Token OAuth do Google nao disponivel. Execute '/auth google' no CLI."}
        try:
            response = requests.get(
                "https://generativelanguage.googleapis.com/v1beta/models",
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
            models = sorted(m.get("name", "").replace("models/", "") for m in data.get("models", []) if m.get("name"))
            return {"provider": provider, "models": models}
        except Exception as exc:
            return {"error": f"Falha ao listar modelos Google via OAuth: {exc}"}

    if provider == "deepseek":
        api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            return {"error": "DEEPSEEK_API_KEY n\u00e3o configurada."}
        try:
            response = requests.get(
                "https://api.deepseek.com/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
            models = sorted(m.get("id", "") for m in data.get("data", []) if m.get("id"))
            return {"provider": provider, "models": models}
        except Exception as exc:
            return {"error": f"Falha ao listar modelos DeepSeek: {exc}"}

    if provider == "mistral":
        api_key = os.getenv("MISTRAL_API_KEY")
        if not api_key:
            return {"error": "MISTRAL_API_KEY n\u00e3o configurada."}
        try:
            response = requests.get(
                "https://api.mistral.ai/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
            models = sorted(m.get("id", "") for m in data.get("data", []) if m.get("id"))
            return {"provider": provider, "models": models}
        except Exception as exc:
            return {"error": f"Falha ao listar modelos Mistral: {exc}"}

    if provider == "ollama":
        host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
        try:
            response = requests.get(
                f"{host.rstrip('/')}/api/tags",
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()
            models = sorted(m.get("name", "") for m in data.get("models", []) if m.get("name"))
            return {"provider": provider, "models": models}
        except Exception as exc:
            return {"error": f"Falha ao listar modelos Ollama: {exc}"}

    if provider == "opencode_go":
        api_key = os.getenv("OPENCODE_GO_API_KEY")
        base_url = os.getenv("OPENCODE_GO_BASE_URL", "https://opencode.ai/zen/go/v1")
        if not api_key:
            return {"error": "OPENCODE_GO_API_KEY n\u00e3o configurada."}
        try:
            response = requests.get(
                f"{base_url.rstrip('/')}/models",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "x-opencode-session": "zeus-session",
                },
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
            # OpenAI-compatible /v1/models returns {"data": [{"id": ...}]}
            if "data" in data and isinstance(data["data"], list):
                models = sorted(m.get("id", "") for m in data["data"] if m.get("id"))
            else:
                models = sorted(data.keys()) if isinstance(data, dict) else []
            return {"provider": provider, "models": models}
        except Exception as exc:
            return {"error": f"Falha ao listar modelos OpenCode Go: {exc}"}

    return {"error": f"Provider '{provider}' n\u00e3o suportado para listagem din\u00e2mica."}


register_tool(
    name="get_zeus_config",
    description="Retorna a configuração atual do Zeus (Provedor LLM, modelo ativo, status das chaves de API e arquivo de config).",
    parameters={"type": "object", "properties": {}},
    handler=get_zeus_config,
    tags=["config", "system"],
)

register_tool(
    name="update_zeus_config",
    description="Atualiza uma variável de configuração ou chave de API no arquivo .env do Zeus e em memória (ex: GEMINI_API_KEY, ZEUS_MODEL, ZEUS_PROVIDER). Configurações do Zeus como max_turns são salvas no config.yaml.",
    parameters={
        "type": "object",
        "properties": {
            "key": {"type": "string", "description": "Nome da variável de ambiente ou config (ex: GEMINI_API_KEY, ZEUS_MODEL, ZEUS_PROVIDER, max_turns)"},
            "value": {"type": "string", "description": "Valor da chave de API ou configuração"},
        },
        "required": ["key", "value"],
    },
    handler=update_zeus_config,
    tags=["config", "system"],
)

register_tool(
    name="list_available_models",
    description="Lista os provedores LLM e modelos disponíveis para uso no Zeus.",
    parameters={
        "type": "object",
        "properties": {
            "provider": {"type": "string", "description": "Opcional: Filtrar por provedor (ex: google, openrouter, opencode_go)"},
        },
    },
    handler=list_available_models,
    tags=["config", "system"],
)
