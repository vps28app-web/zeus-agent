"""Interactive setup helpers for Zeus gateways."""

import os
import sys
from pathlib import Path
from typing import Optional

import requests


def _get_input(prompt: str, default: Optional[str] = None, secret: bool = False) -> str:
    """Read a line from stdin, optionally masking secrets."""
    if default:
        prompt = f"{prompt} [{default}]: "
    else:
        prompt = f"{prompt}: "
    if secret:
        try:
            import getpass
            value = getpass.getpass(prompt)
        except Exception:
            value = input(prompt)
    else:
        value = input(prompt)
    return value.strip() or (default or "")


def _project_env_path() -> Path:
    """Return the path to the project's .env file."""
    return Path.cwd() / ".env"


def _read_env_file(path: Path) -> str:
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def _write_env_file(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def _upsert_env_var(content: str, key: str, value: str) -> str:
    """Add or replace an environment variable in the .env content."""
    lines = content.splitlines(keepends=True)
    # Ensure last line ends with newline
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


def _test_telegram_token(token: str) -> bool:
    """Verify that the Telegram bot token is valid."""
    try:
        response = requests.get(
            f"https://api.telegram.org/bot{token}/getMe",
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()
        if data.get("ok"):
            bot = data.get("result", {})
            print(f"Bot OK: @{bot.get('username')} ({bot.get('first_name')})")
            return True
        print(f"Telegram API error: {data}")
        return False
    except Exception as e:
        print(f"Failed to validate Telegram token: {e}")
        return False


def setup_telegram(token: str | None = None, chat_id: str | None = None, skip_validation: bool = False) -> bool:
    """Interactively configure the Telegram gateway and save to .env."""
    if token is None:
        print("\n=== Configurar gateway do Telegram ===")
        print("1. Crie um bot no @BotFather e copie o token.")
        print("2. Envie /start para o bot no Telegram.")
        print("3. Descubra seu chat ID em https://api.telegram.org/bot<TOKEN>/getUpdates")
        print()
        token = _get_input("Bot token", secret=True)

    if not token:
        print("Token obrigatório.")
        return False

    if not skip_validation and not _test_telegram_token(token):
        retry = _get_input("Token parece inválido. Deseja continuar mesmo assim? (s/N)")
        if retry.lower() not in ("s", "sim", "y", "yes"):
            return False

    if chat_id is None:
        chat_id = _get_input("Chat ID permitido")
    if not chat_id:
        print("Chat ID obrigatório para segurança.")
        return False

    try:
        int(chat_id)
    except ValueError:
        print("Chat ID deve ser um número inteiro.")
        return False

    env_path = _project_env_path()
    content = _read_env_file(env_path)
    content = _upsert_env_var(content, "TELEGRAM_BOT_TOKEN", token)
    content = _upsert_env_var(content, "TELEGRAM_ALLOWED_USERS", chat_id)
    _write_env_file(env_path, content)

    print(f"\nConfiguração salva em {env_path}")
    return True


def setup_whatsapp(base_url: str | None = None, allowed_numbers: str | None = None) -> bool:
    """Interactively configure the WhatsApp gateway and save to .env."""
    if base_url is None and allowed_numbers is None:
        print("\n=== Configurar gateway do WhatsApp ===")
        print("1. A ponte Baileys deve estar rodando.")
        print("2. Escaneie o QR code com WhatsApp > Linked Devices.")
        print("3. Use o JID do número permitido (ex: 5511999999999@s.whatsapp.net).")
        print()

    if base_url is None:
        base_url = _get_input("URL da ponte Baileys", default="http://127.0.0.1:9877")
    if allowed_numbers is None:
        allowed_numbers = _get_input("Número permitido (jid)")
    if not allowed_numbers:
        print("Número permitido obrigatório.")
        return False

    env_path = _project_env_path()
    content = _read_env_file(env_path)
    content = _upsert_env_var(content, "ZEUS_WHATSAPP_URL", base_url)
    content = _upsert_env_var(content, "ZEUS_WHATSAPP_ALLOWED_NUMBERS", allowed_numbers)
    _write_env_file(env_path, content)

    print(f"\nConfiguração salva em {env_path}")
    return True


def setup_discord(token: str | None = None, allowed_user_ids: str | None = None, allowed_channel_ids: str | None = None) -> bool:
    """Interactively configure the Discord gateway and save to .env."""
    if token is None and allowed_user_ids is None and allowed_channel_ids is None:
        print("\n=== Configurar gateway do Discord ===")
        print("1. Crie um app em https://discord.com/developers/applications")
        print("2. Adicione um Bot e habilite Message Content Intent.")
        print("3. Copie o token do bot.")
        print()

    if token is None:
        token = _get_input("Bot token", secret=True)
    if not token:
        print("Token obrigatório.")
        return False

    if allowed_user_ids is None:
        allowed_user_ids = _get_input("User ID permitido (opcional)")
    if allowed_channel_ids is None:
        allowed_channel_ids = _get_input("Channel ID permitido (opcional)")

    env_path = _project_env_path()
    content = _read_env_file(env_path)
    content = _upsert_env_var(content, "ZEUS_DISCORD_TOKEN", token)
    if allowed_user_ids:
        content = _upsert_env_var(content, "ZEUS_DISCORD_ALLOWED_USER_IDS", allowed_user_ids)
    if allowed_channel_ids:
        content = _upsert_env_var(content, "ZEUS_DISCORD_ALLOWED_CHANNEL_IDS", allowed_channel_ids)
    _write_env_file(env_path, content)

    print(f"\nConfiguração salva em {env_path}")
    return True


def is_configured(platform: str) -> bool:
    """Check whether the given platform has the minimum required env vars."""
    if platform == "telegram":
        return bool(
            os.getenv("ZEUS_TELEGRAM_TOKEN")
            or os.getenv("TELEGRAM_BOT_TOKEN")
        )
    if platform == "whatsapp":
        return bool(os.getenv("ZEUS_WHATSAPP_ALLOWED_NUMBERS"))
    if platform == "discord":
        return bool(os.getenv("ZEUS_DISCORD_TOKEN"))
    return False


def ensure_configured(platform: str) -> bool:
    """If not configured, run the interactive setup for the platform."""
    if is_configured(platform):
        return True
    if platform == "telegram":
        return setup_telegram()
    if platform == "whatsapp":
        return setup_whatsapp()
    if platform == "discord":
        return setup_discord()
    return False
