"""Interactive setup helpers for Zeus gateways."""

import os
from pathlib import Path
from typing import Optional

import requests


def _get_input(prompt: str, default: Optional[str] = None, secret: bool = False) -> str:
    """Read a line from stdin, optionally masking secrets."""
    try:
        from prompt_toolkit import prompt as pt_prompt
        if default:
            prompt_text = f"{prompt} [{default}]: "
        else:
            prompt_text = f"{prompt}: "
        value = pt_prompt(prompt_text, is_password=secret)
        return value.strip() or (default or "")
    except KeyboardInterrupt:
        raise
    except Exception:
        pass

    if default:
        prompt = f"{prompt} [{default}]: "
    else:
        prompt = f"{prompt}: "
    if secret:
        try:
            import getpass
            value = getpass.getpass(prompt)
        except KeyboardInterrupt:
            raise
        except Exception:
            value = input(prompt)
    else:
        value = input(prompt)
    return value.strip() or (default or "")


def _project_env_path() -> Path:
    """Return the default Zeus configuration env file path."""
    config_dir = Path(os.getenv("ZEUS_HOME", str(Path.home() / ".zeus"))).expanduser()
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir / ".env"


def _read_env_file(path: Path) -> str:
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def _write_env_file(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    if os.name != "nt":
        path.chmod(0o600)


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
    print("Validando token com Telegram...", end=" ", flush=True)
    try:
        response = requests.get(
            f"https://api.telegram.org/bot{token}/getMe",
            timeout=5,
        )
        response.raise_for_status()
        data = response.json()
        if data.get("ok"):
            bot = data.get("result", {})
            print(f"OK: @{bot.get('username')} ({bot.get('first_name')})")
            return True
        print(f"erro: {data}")
        return False
    except requests.exceptions.Timeout:
        print("demorou demais (timeout).")
        return False
    except Exception as e:
        print(f"falhou: {e}")
        return False


def setup_telegram(token: str | None = None, chat_id: str | None = None, skip_validation: bool = False) -> bool:
    """Interactively configure the Telegram gateway and save to .env."""
    try:
        return _setup_telegram(token, chat_id, skip_validation)
    except KeyboardInterrupt:
        print("\n\nConfiguração cancelada pelo usuário.")
        return False


def _setup_telegram(token: str | None = None, chat_id: str | None = None, skip_validation: bool = False) -> bool:
    """Internal implementation of Telegram setup."""
    if token is None:
        print("\n=== Configurar gateway do Telegram ===")
        print("1. Crie um bot no @BotFather e copie o token.")
        print("2. Envie /start para o bot no Telegram.")
        print("3. Descubra seu chat ID em https://api.telegram.org/bot<TOKEN>/getUpdates")
        print("   (ou use --skip-validation para pular a verificação)")
        print()
        token = _get_input("Bot token", secret=True)

    if not token:
        print("Token obrigatório.")
        return False

    if not skip_validation and not _test_telegram_token(token):
        print()
        print("Não foi possível validar o token. Pode ser:")
        print("  - token copiado errado")
        print("  - conexão lenta com api.telegram.org")
        print("  - bot ainda não criado ou revogado")
        print()
        retry = _get_input("Deseja continuar mesmo assim? (s/N)")
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
    print("\nPara iniciar o gateway, rode:")
    print("  zeus gateway start telegram")
    return True


def setup_whatsapp(base_url: str | None = None, allowed_numbers: str | None = None) -> bool:
    """Interactively configure the WhatsApp gateway and save to .env."""
    try:
        return _setup_whatsapp(base_url, allowed_numbers)
    except KeyboardInterrupt:
        print("\n\nConfiguração cancelada pelo usuário.")
        return False


def _setup_whatsapp(base_url: str | None = None, allowed_numbers: str | None = None) -> bool:
    """Internal implementation of WhatsApp setup."""
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
    try:
        return _setup_discord(token, allowed_user_ids, allowed_channel_ids)
    except KeyboardInterrupt:
        print("\n\nConfiguração cancelada pelo usuário.")
        return False


def _setup_discord(token: str | None = None, allowed_user_ids: str | None = None, allowed_channel_ids: str | None = None) -> bool:
    """Internal implementation of Discord setup."""
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


def setup_instagram(
    account_id: str | None = None,
    access_token: str | None = None,
    app_secret: str | None = None,
    verify_token: str | None = None,
    public_webhook_url: str | None = None,
) -> bool:
    """Configure the official Instagram Messaging API webhook integration."""
    values = {
        "ZEUS_INSTAGRAM_ACCOUNT_ID": account_id,
        "ZEUS_INSTAGRAM_ACCESS_TOKEN": access_token,
        "ZEUS_INSTAGRAM_APP_SECRET": app_secret,
        "ZEUS_INSTAGRAM_VERIFY_TOKEN": verify_token,
        "ZEUS_INSTAGRAM_PUBLIC_WEBHOOK_URL": public_webhook_url,
    }
    secret_names = {
        "ZEUS_INSTAGRAM_ACCESS_TOKEN",
        "ZEUS_INSTAGRAM_APP_SECRET",
        "ZEUS_INSTAGRAM_VERIFY_TOKEN",
    }
    prompts = {
        "ZEUS_INSTAGRAM_ACCOUNT_ID": "Instagram Professional Account ID",
        "ZEUS_INSTAGRAM_ACCESS_TOKEN": "Instagram access token",
        "ZEUS_INSTAGRAM_APP_SECRET": "Meta App Secret",
        "ZEUS_INSTAGRAM_VERIFY_TOKEN": "Webhook verify token (choose a private string)",
        "ZEUS_INSTAGRAM_PUBLIC_WEBHOOK_URL": "Public HTTPS webhook URL (use path /webhook)",
    }
    for name in values:
        if values[name] is None:
            values[name] = os.getenv(name) or _get_input(
                prompts[name], secret=name in secret_names
            )
        if not values[name]:
            print(f"{name} é obrigatório.")
            return False

    from urllib.parse import urlparse

    parsed_url = urlparse(values["ZEUS_INSTAGRAM_PUBLIC_WEBHOOK_URL"] or "")
    if parsed_url.scheme != "https" or not parsed_url.netloc or parsed_url.path != "/webhook":
        print("A URL do webhook deve ser HTTPS público e usar o caminho /webhook.")
        return False

    env_path = _project_env_path()
    content = _read_env_file(env_path)
    for name, value in values.items():
        content = _upsert_env_var(content, name, value or "")
        os.environ[name] = value or ""
    _write_env_file(env_path, content)

    print(f"\nConfiguração do Instagram salva em {env_path}")
    print("No painel Meta, habilite o campo de webhook `messages` e configure a URL de callback.")
    print("A conta deve ser Profissional, o app deve ter acesso a instagram_manage_messages e estar publicado.")
    print("Para iniciar: zeus gateway start instagram")
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
    if platform == "instagram":
        return all(os.getenv(name) for name in (
            "ZEUS_INSTAGRAM_ACCESS_TOKEN",
            "ZEUS_INSTAGRAM_ACCOUNT_ID",
            "ZEUS_INSTAGRAM_APP_SECRET",
            "ZEUS_INSTAGRAM_VERIFY_TOKEN",
            "ZEUS_INSTAGRAM_PUBLIC_WEBHOOK_URL",
        ))
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
    if platform == "instagram":
        return setup_instagram()
    return False
