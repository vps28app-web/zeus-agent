"""Interactive setup commands for Zeus (model/provider config)."""

import os
import sys
from pathlib import Path
from typing import Optional


MODEL_PRESETS = {
    "opencode_go": [
        ("kimi-k2.7-code", "Kimi K2.5 Code (recomendado para código)"),
    ],
    "openrouter": [
        ("openrouter/auto", "Auto (escolha automática)"),
        ("anthropic/claude-sonnet-4", "Claude Sonnet 4"),
        ("openai/gpt-4o", "GPT-4o"),
        ("google/gemini-2.5-pro", "Gemini 2.5 Pro"),
        ("deepseek/deepseek-chat", "DeepSeek Chat"),
        ("mistralai/mistral-large", "Mistral Large"),
    ],
    "openai": [
        ("gpt-4o", "GPT-4o"),
        ("gpt-4o-mini", "GPT-4o Mini"),
        ("o3-mini", "o3 Mini"),
    ],
    "anthropic": [
        ("claude-sonnet-4-20250514", "Claude Sonnet 4"),
        ("claude-opus-4-20250514", "Claude Opus 4"),
        ("claude-haiku-3-5-20241022", "Claude Haiku 3.5"),
    ],
    "google": [
        ("gemini-2.5-pro-exp-03-25", "Gemini 2.5 Pro"),
        ("gemini-2.0-flash", "Gemini 2.0 Flash"),
    ],
    "deepseek": [
        ("deepseek-chat", "DeepSeek Chat"),
        ("deepseek-reasoner", "DeepSeek Reasoner"),
    ],
    "mistral": [
        ("mistral-large-latest", "Mistral Large"),
        ("mistral-small-latest", "Mistral Small"),
    ],
    "ollama": [
        ("llama3.1", "Llama 3.1"),
        ("qwen2.5-coder", "Qwen 2.5 Coder"),
        ("phi4", "Phi-4"),
    ],
}

PROVIDER_ENV_VARS = {
    "opencode_go": ("OPENCODE_GO_API_KEY", "OPENCODE_GO_BASE_URL"),
    "openrouter": ("OPENROUTER_API_KEY",),
    "openai": ("OPENAI_API_KEY",),
    "anthropic": ("ANTHROPIC_API_KEY",),
    "google": ("GOOGLE_API_KEY",),
    "deepseek": ("DEEPSEEK_API_KEY",),
    "mistral": ("MISTRAL_API_KEY",),
    "ollama": (),
}


def _get_input(prompt: str, default: Optional[str] = None, secret: bool = False) -> str:
    """Read a line from stdin, optionally masking secrets."""
    try:
        from prompt_toolkit import prompt as pt_prompt
        prompt_text = f"{prompt} [{default}]: " if default else f"{prompt}: "
        value = pt_prompt(prompt_text, is_password=secret)
        return value.strip() or (default or "")
    except KeyboardInterrupt:
        raise
    except Exception:
        pass

    prompt_text = f"{prompt} [{default}]: " if default else f"{prompt}: "
    if secret:
        try:
            import getpass
            value = getpass.getpass(prompt_text)
        except KeyboardInterrupt:
            raise
        except Exception:
            value = input(prompt_text)
    else:
        value = input(prompt_text)
    return value.strip() or (default or "")


def _project_env_path() -> Path:
    home = os.getenv("ZEUS_HOME", os.path.expanduser("~/.zeus"))
    path = Path(home)
    path.mkdir(parents=True, exist_ok=True)
    return path / ".env"


def _read_env_file(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _write_env_file(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def _upsert_env_var(content: str, key: str, value: str) -> str:
    """Add or replace an environment variable in the .env content."""
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

    return "".join(lines)


def _current_provider_and_model() -> tuple[str, str]:
    provider = os.getenv("ZEUS_PROVIDER", "openrouter")
    model = os.getenv("ZEUS_MODEL", "openrouter/auto")
    return provider, model


def setup_model() -> bool:
    """Interactively configure LLM provider and model."""
    try:
        return _setup_model()
    except KeyboardInterrupt:
        print("\n\nConfiguração cancelada pelo usuário.")
        return False


def _setup_model() -> bool:
    current_provider, current_model = _current_provider_and_model()

    print("\n=== Configurar provedor e modelo ===\n")
    providers = list(MODEL_PRESETS.keys())

    while True:
        print("Provedores disponíveis:")
        for i, name in enumerate(providers, 1):
            marker = "  <- atual" if name == current_provider else ""
            print(f"  {i}. {name}{marker}")

        choice = _get_input("\nEscolha o provedor (número ou nome)", default=current_provider)
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(providers):
                provider = providers[idx]
                break
        elif choice in providers:
            provider = choice
            break
        print(f"Opção inválida: {choice}. Tente novamente.\n")

    models = MODEL_PRESETS[provider]

    while True:
        print(f"\nModelos disponíveis para {provider}:")
        for i, (model_id, description) in enumerate(models, 1):
            marker = "  <- atual" if model_id == current_model else ""
            print(f"  {i}. {model_id} - {description}{marker}")
        print("  0. Outro (digite manualmente)")

        model_choice = _get_input("\nEscolha o modelo (número ou id)", default="1")
        if model_choice == "0":
            model = _get_input("Model ID")
            if model:
                break
            print("Model ID não pode ser vazio. Tente novamente.")
            continue
        if model_choice.isdigit():
            idx = int(model_choice) - 1
            if 0 <= idx < len(models):
                model = models[idx][0]
                break
        elif model_choice in [m[0] for m in models]:
            model = model_choice
            break
        print(f"Opção inválida: {model_choice}. Tente novamente.")

    # Ask for API keys if not already present
    env_vars = PROVIDER_ENV_VARS.get(provider, ())
    env_path = _project_env_path()
    content = _read_env_file(env_path)

    for var in env_vars:
        current = os.getenv(var)
        if current:
            print(f"{var} já configurado.")
            continue
        value = _get_input(f"{var} (deixe em branco para pular)", secret=True)
        if value:
            content = _upsert_env_var(content, var, value)

    content = _upsert_env_var(content, "ZEUS_PROVIDER", provider)
    content = _upsert_env_var(content, "ZEUS_MODEL", model)
    _write_env_file(env_path, content)

    print(f"\nConfiguração salva em {env_path}")
    print(f"  Provedor: {provider}")
    print(f"  Modelo:   {model}")
    print("\nReinicie o Zeus CLI/gateway para usar as novas configurações.")
    return True


if __name__ == "__main__":
    setup_model()
