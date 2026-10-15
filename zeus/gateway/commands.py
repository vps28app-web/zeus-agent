"""Safe, non-LLM admin commands for configured messaging gateways."""

import os


def _configured(*names: str) -> bool:
    return all(os.getenv(name) for name in names)


def _channel_status() -> dict[str, bool]:
    return {
        "Telegram": _configured(
            "ZEUS_TELEGRAM_TOKEN", "ZEUS_TELEGRAM_ALLOWED_CHAT_IDS"
        ) or _configured("TELEGRAM_BOT_TOKEN", "TELEGRAM_ALLOWED_USERS"),
        "WhatsApp": _configured("ZEUS_WHATSAPP_ALLOWED_NUMBERS"),
        "Discord": _configured("ZEUS_DISCORD_TOKEN"),
        "Instagram": _configured(
            "ZEUS_INSTAGRAM_ACCESS_TOKEN",
            "ZEUS_INSTAGRAM_ACCOUNT_ID",
            "ZEUS_INSTAGRAM_APP_SECRET",
            "ZEUS_INSTAGRAM_VERIFY_TOKEN",
            "ZEUS_INSTAGRAM_PUBLIC_WEBHOOK_URL",
        ),
    }


def handle_zeus_command(text: str) -> str | None:
    """Return an admin response for !zeus commands, or None for regular text."""
    text = text.strip()
    if text != "!zeus" and not text.startswith("!zeus "):
        return None

    parts = text.split(maxsplit=1)
    subcommand = parts[1].strip().lower() if len(parts) == 2 else "help"

    if subcommand in ("help", "menu", ""):
        return (
            "Zeus está online. Comandos:\n"
            "!zeus status — mostra provedor/modelo e integrações configuradas\n"
            "!zeus provider <nome> [modelo] — troca provider/modelo se a chave já existir\n"
            "!zeus model <id> — troca somente o modelo\n"
            "!zeus setup — instruções para abrir a configuração local\n"
            "As chaves são inseridas apenas neste terminal, em prompts mascarados."
        )

    if subcommand in ("setup", "config", "configure"):
        return (
            "Para configurar o Zeus com segurança, execute `zeus setup` no terminal local.\n"
            "A configuração de provedor/modelo e gateways usa prompts mascarados; não envie chaves por mensagem.\n"
            "Instagram exige uma conta Profissional, app/token da Meta e webhook HTTPS público."
        )

    if subcommand in ("status", "check"):
        provider = os.getenv("ZEUS_PROVIDER", "não configurado")
        model = os.getenv("ZEUS_MODEL", "não configurado")
        from zeus.cli.setup_commands import PROVIDER_ENV_VARS
        required_provider_vars = PROVIDER_ENV_VARS.get(provider, ())
        provider_ready = bool(required_provider_vars) and all(
            os.getenv(name)
            for name in required_provider_vars
            if any(marker in name for marker in ("KEY", "SECRET", "TOKEN"))
        )
        if not required_provider_vars:
            provider_ready = provider == "ollama"
        channels = _channel_status()
        channel_lines = [
            f"{name}: {'configurado' if configured else 'não configurado'}"
            for name, configured in channels.items()
        ]
        return (
            f"Zeus status\nProvedor: {provider}\nModelo: {model}\n"
            f"Credenciais do provedor: {'configuradas' if provider_ready else 'não configuradas'}\n"
            + "\n".join(channel_lines)
        )

    if subcommand.startswith("provider "):
        args = subcommand.split()
        provider = args[1]
        from zeus.cli.setup_commands import MODEL_PRESETS, PROVIDER_ENV_VARS
        if provider not in PROVIDER_ENV_VARS:
            return "Provider desconhecido. Use !zeus para ver as opções ou `zeus setup` no terminal."
        required = [
            name for name in PROVIDER_ENV_VARS[provider]
            if any(marker in name for marker in ("KEY", "SECRET", "TOKEN"))
        ]
        missing = [name for name in required if not os.getenv(name)]
        if missing:
            return (
                f"Falta(m) {', '.join(missing)}. Execute `zeus setup` no terminal; "
                "as chaves não são solicitadas por mensagem."
            )
        model = args[2] if len(args) > 2 else MODEL_PRESETS[provider][0][0]
        from zeus.tools.config_tools import update_zeus_config
        update_zeus_config("ZEUS_PROVIDER", provider)
        update_zeus_config("ZEUS_MODEL", model)
        return f"Provider alterado para {provider}; modelo: {model}."

    if subcommand.startswith("model "):
        model = subcommand.split(maxsplit=1)[1].strip()
        if not model:
            return "Uso: !zeus model <id-do-modelo>"
        from zeus.tools.config_tools import update_zeus_config
        update_zeus_config("ZEUS_MODEL", model)
        return f"Modelo alterado para {model}."

    return "Comando desconhecido. Envie !zeus para ver as opções."
