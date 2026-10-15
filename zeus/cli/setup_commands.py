"""Interactive setup commands for Zeus (model/provider config)."""

import os
import re
import shutil
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.formatted_text import ANSI

from zeus.tools.config_tools import fetch_models

MODEL_PRESETS = {
    "opencode_go": [
        ("deepseek-v4-pro", "DeepSeek V4 Pro (padrão)"),
        ("kimi-k2.7-code", "Kimi K2.5 Code"),
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
    "google_api": [
        ("gemini-3.6-flash", "Gemini 3.6 Flash via API key"),
        ("gemini-flash-latest", "Gemini Flash Latest via API key"),
        ("gemini-3.5-flash", "Gemini 3.5 Flash via API key"),
    ],
    "google_auth": [
        ("gemini-3.6-flash", "Gemini 3.6 Flash via OAuth browser"),
        ("gemini-flash-latest", "Gemini Flash Latest via OAuth browser"),
        ("gemini-3.5-flash", "Gemini 3.5 Flash via OAuth browser"),
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
    "google_api": ("GEMINI_API_KEY",),
    "google_auth": ("GOOGLE_OAUTH_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_SECRET"),
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
    if os.name != "nt":
        path.chmod(0o600)


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


def _color(text: str, code: str | int) -> str:
    """Wrap text in ANSI color codes."""
    if os.getenv("NO_COLOR", "").strip():
        return text
    return f"\033[{code}m{text}\033[0m"


def _visible_width(text: str) -> int:
    """Return visible width ignoring ANSI escape codes."""
    return len(re.sub(r"\x1b\[[0-9;]*m", "", text))


def _truncate_visible(text: str, width: int, suffix: str = "...") -> str:
    """Truncate text so visible width <= width, preserving ANSI codes."""
    if _visible_width(text) <= width:
        return text
    suffix_width = _visible_width(suffix)
    avail = max(0, width - suffix_width)
    plain = re.sub(r"\x1b\[[0-9;]*m", "", text)
    leading_codes = ""
    match = re.match(r"(\x1b\[[0-9;]*m)+", text)
    if match:
        leading_codes = match.group(0)
    truncated = plain[:avail]
    return f"{leading_codes}{truncated}{suffix}\033[0m"


def _pad_left(text: str, width: int) -> str:
    vis = _visible_width(text)
    if vis > width:
        text = _truncate_visible(text, width)
        vis = _visible_width(text)
    pad = width - vis
    return text + " " * pad


def _pad_center(text: str, width: int) -> str:
    vis = _visible_width(text)
    if vis > width:
        text = _truncate_visible(text, width)
        vis = _visible_width(text)
    pad = width - vis
    left = pad // 2
    right = pad - left
    return " " * left + text + " " * right


class _ProviderCompleter(Completer):
    """ prompt_toolkit completer for provider selection."""

    def __init__(self, providers: List[str], current_provider: str):
        self.providers = providers
        self.current_provider = current_provider

    def get_completions(self, document, complete_event) -> Iterable[Completion]:
        text = document.text_before_cursor.lower()
        for name in self.providers:
            display_meta = ""
            required_vars = PROVIDER_ENV_VARS.get(name, ())
            if name == "ollama":
                display_meta = "local"
            elif required_vars and all(os.getenv(v) for v in required_vars):
                display_meta = "chave configurada"
            elif required_vars:
                missing = ", ".join(v for v in required_vars if not os.getenv(v))
                display_meta = f"faltando: {missing}"
            if name == self.current_provider:
                display_meta = f"atual - {display_meta}" if display_meta else "atual"
            if text in name.lower():
                yield Completion(
                    name,
                    start_position=-len(document.text_before_cursor),
                    display=name,
                    display_meta=display_meta,
                )


class _ModelCompleter(Completer):
    """prompt_toolkit completer for model selection."""

    def __init__(self, models: List[Tuple[str, str]], current_model: str):
        self.models = models
        self.current_model = current_model

    def get_completions(self, document, complete_event) -> Iterable[Completion]:
        text = document.text_before_cursor.lower()
        for model_id, description in self.models:
            display_meta = description
            if model_id == self.current_model:
                display_meta = f"atual - {display_meta}" if display_meta else "atual"
            if text in model_id.lower() or text in description.lower():
                yield Completion(
                    model_id,
                    start_position=-len(document.text_before_cursor),
                    display=model_id,
                    display_meta=display_meta,
                )


def _select_provider_interactive(providers: List[str], current_provider: str) -> Optional[str]:
    """Interactive provider selection with arrow/tab completion and filtering."""
    _print_provider_menu(providers, current_provider)
    completer = _ProviderCompleter(providers, current_provider)
    session = PromptSession(
        ANSI(_color("\nEscolha o provedor: ", 33)),
        completer=completer,
        complete_while_typing=True,
    )
    try:
        choice = session.prompt().strip()
    except (EOFError, KeyboardInterrupt):
        return None
    if not choice:
        return current_provider
    if choice in providers:
        return choice
    # Try numeric selection
    if choice.isdigit():
        idx = int(choice) - 1
        if 0 <= idx < len(providers):
            return providers[idx]
    print(f"Opção inválida: {choice}. Mantendo {current_provider}.")
    return current_provider


def _print_provider_menu(providers: List[str], current_provider: str) -> None:
    """Print a boxed menu of providers."""
    term_width = shutil.get_terminal_size().columns
    inner_width = max(40, min(term_width - 8, 90))
    title = " Provedores disponíveis "
    title_vis = len(title)
    side = max(2, (inner_width - title_vis) // 2)
    top = _color("╔" + "═" * side + title + "═" * (inner_width - side - title_vis) + "╗", 34)
    bottom = _color("╚" + "═" * inner_width + "╝", 34)

    print()
    print(top)
    print(_color("║", 34) + _pad_center(f"Atual: {current_provider}", inner_width) + _color("║", 34))
    print(_color("║", 34) + " " * inner_width + _color("║", 34))

    for i, name in enumerate(providers, 1):
        marker = "✓" if name == current_provider else " "
        required_vars = PROVIDER_ENV_VARS.get(name, ())
        if name == "ollama":
            key_status = "(local)"
        elif required_vars and all(os.getenv(v) for v in required_vars):
            key_status = "✅"
        elif required_vars:
            missing = ", ".join(v for v in required_vars if not os.getenv(v))
            key_status = f"⚠️ {missing}"
        else:
            key_status = ""
        left_text = f"{marker} {i}. {name}"
        right_text = key_status
        avail = inner_width - 2
        if right_text:
            full_line = f"{left_text} {right_text}"
        else:
            full_line = left_text
        full_width = _visible_width(full_line)
        if full_width > avail:
            line = _truncate_visible(full_line, avail)
        else:
            line = full_line + " " * (avail - full_width)
        print(_color("║", 34) + " " + line + " " + _color("║", 34))

    footer = " Digite nome/número, use Tab/↑↓ para navegar, Enter para confirmar"
    footer = _truncate_visible(footer, inner_width - 2)
    print(_color("║", 34) + " " + _pad_left(footer, inner_width - 2) + " " + _color("║", 34))
    print(bottom)


def _select_model_interactive(
    provider: str,
    models: List[Tuple[str, str]],
    current_model: str,
    source: str,
) -> Optional[str]:
    """Interactive model selection with arrow/tab completion and filtering."""
    _print_model_menu(provider, models, current_model, source)
    completer = _ModelCompleter(models, current_model)
    session = PromptSession(
        ANSI(_color("\nEscolha o modelo: ", 33)),
        completer=completer,
        complete_while_typing=True,
    )
    try:
        choice = session.prompt().strip()
    except (EOFError, KeyboardInterrupt):
        return None
    if not choice:
        return current_model
    model_ids = [m[0] for m in models]
    if choice in model_ids:
        return choice
    if choice.isdigit():
        idx = int(choice) - 1
        if 0 <= idx < len(models):
            return models[idx][0]
    print(f"Opção inválida: {choice}. Mantendo {current_model}.")
    return current_model


def _print_model_menu(
    provider: str,
    models: List[Tuple[str, str]],
    current_model: str,
    source: str,
) -> None:
    """Print a boxed menu of models (paginated if too large)."""
    term_width = shutil.get_terminal_size().columns
    inner_width = max(40, min(term_width - 8, 90))
    title = f" Modelos {provider} ({source}) "
    title_vis = len(title)
    side = max(2, (inner_width - title_vis) // 2)
    top = _color("╔" + "═" * side + title + "═" * (inner_width - side - title_vis) + "╗", 34)
    bottom = _color("╚" + "═" * inner_width + "╝", 34)

    print()
    print(top)
    print(_color("║", 34) + _pad_center(f"Modelo atual: {current_model}", inner_width) + _color("║", 34))
    print(_color("║", 34) + " " * inner_width + _color("║", 34))

    for i, (model_id, description) in enumerate(models[:25], 1):
        marker = " ✓" if model_id == current_model else " "
        line = f"{marker} {i}. {model_id}"
        if description:
            line += f" - {description}"
        line = _truncate_visible(line, inner_width - 2)
        print(_color("║", 34) + " " + _pad_left(line, inner_width - 2) + " " + _color("║", 34))

    if len(models) > 25:
        remaining = len(models) - 25
        line = f"... e mais {remaining} modelos (filtre digitando)"
        line = _truncate_visible(line, inner_width - 2)
        print(_color("║", 34) + " " + _pad_left(line, inner_width - 2) + " " + _color("║", 34))

    footer = " Digite nome/número, use Tab/↑↓ para navegar, Enter para confirmar"
    footer = _truncate_visible(footer, inner_width - 2)
    print(_color("║", 34) + " " + _pad_left(footer, inner_width - 2) + " " + _color("║", 34))
    print(bottom)


def setup_model() -> bool:
    """Interactively configure LLM provider and model."""
    try:
        return _setup_model()
    except KeyboardInterrupt:
        print("\n\nConfiguração cancelada pelo usuário.")
        return False


def _setup_model() -> bool:
    current_provider, current_model = _current_provider_and_model()
    providers = list(MODEL_PRESETS.keys())

    provider = _select_provider_interactive(providers, current_provider)
    if provider is None:
        print("Configuração cancelada.")
        return False

    preset_models = MODEL_PRESETS[provider]
    fetched = fetch_models(provider)
    if "error" not in fetched and fetched.get("models"):
        dynamic_models = fetched["models"]
        preset_map = {m[0]: m[1] for m in preset_models}
        models: List[Tuple[str, str]] = [(mid, preset_map.get(mid, "")) for mid in dynamic_models]
        source = "via API"
    else:
        models = list(preset_models)
        source = "preset"

    model = _select_model_interactive(provider, models, current_model, source)
    if model is None:
        print("Configuração cancelada.")
        return False
    if model == "0":
        model = _get_input("Model ID")
        if not model:
            print("Model ID não pode ser vazio. Configuração cancelada.")
            return False

    env_vars = PROVIDER_ENV_VARS.get(provider, ())
    env_path = _project_env_path()
    content = _read_env_file(env_path)

    for var in env_vars:
        if os.getenv(var):
            continue
        secret = any(marker in var.upper() for marker in ("KEY", "SECRET", "TOKEN"))
        value = _get_input(f"{var} (deixe em branco para pular)", secret=secret)
        if value:
            content = _upsert_env_var(content, var, value)
            os.environ[var] = value

    # For Google OAuth, ensure a valid access token (refresh silently or open browser).
    if provider == "google_auth":
        try:
            from zeus.core.google_oauth_desktop import get_access_token
        except Exception:
            pass
        else:
            try:
                get_access_token()
            except Exception as exc:
                print(f"\n{_color('Falha na autenticação Google OAuth:', '1;31')} {exc}")
                return False

    content = _upsert_env_var(content, "ZEUS_PROVIDER", provider)
    content = _upsert_env_var(content, "ZEUS_MODEL", model)
    _write_env_file(env_path, content)

    os.environ["ZEUS_PROVIDER"] = provider
    os.environ["ZEUS_MODEL"] = model

    print(f"\n  Provedor: {provider}")
    print(f"  Modelo:   {model}")
    return True



if __name__ == "__main__":
    setup_model()
