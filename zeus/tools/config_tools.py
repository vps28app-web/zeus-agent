"""Configuration management tools for Zeus framework."""

import os
from pathlib import Path
from typing import Any, Dict, Optional
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

    # Update in memory; keep GEMINI and GOOGLE aliases in sync for router compatibility.
    os.environ[key] = value
    if key == "GEMINI_API_KEY":
        os.environ["GOOGLE_API_KEY"] = value
    elif key == "GOOGLE_API_KEY":
        os.environ["GEMINI_API_KEY"] = value


def get_zeus_config() -> Dict[str, Any]:
    """Retrieve the current Zeus LLM provider, model, and API keys status."""
    keys_to_check = [
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
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
        "api_keys_status": status,
        "config_file": str(_get_env_path()),
    }


def update_zeus_config(key: str, value: str) -> Dict[str, Any]:
    """Update a configuration key or API key in Zeus settings (.env)."""
    key_clean = key.strip().upper()
    val_clean = value.strip()
    if not key_clean:
        return {"error": "Key name cannot be empty"}

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
            return {
                "provider": prov_lower,
                "models": [m[0] for m in MODEL_PRESETS[prov_lower]],
                "details": MODEL_PRESETS[prov_lower],
            }
        return {"error": f"Provider '{provider}' não encontrado.", "available_providers": list(MODEL_PRESETS.keys())}

    return {
        "providers": list(MODEL_PRESETS.keys()),
        "presets": MODEL_PRESETS,
    }


register_tool(
    name="get_zeus_config",
    description="Retorna a configuração atual do Zeus (Provedor LLM, modelo ativo, status das chaves de API e arquivo de config).",
    parameters={"type": "object", "properties": {}},
    handler=get_zeus_config,
    tags=["config", "system"],
)

register_tool(
    name="update_zeus_config",
    description="Atualiza uma variável de configuração ou chave de API no arquivo .env do Zeus e em memória (ex: GEMINI_API_KEY, ZEUS_MODEL, ZEUS_PROVIDER).",
    parameters={
        "type": "object",
        "properties": {
            "key": {"type": "string", "description": "Nome da variável de ambiente (ex: GEMINI_API_KEY, ZEUS_MODEL, ZEUS_PROVIDER)"},
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
