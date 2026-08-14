"""CLI for starting and configuring the Zeus gateway."""

import argparse
import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

from zeus.gateway.discord import DiscordGateway
from zeus.gateway.setup import ensure_configured, is_configured, setup_discord, setup_telegram, setup_whatsapp
from zeus.gateway.telegram import TelegramGateway
from zeus.gateway.whatsapp import WhatsAppGateway


def _load_env() -> None:
    """Load .env from the project root if present."""
    cwd = Path.cwd()
    env_file = cwd / ".env"
    if env_file.exists():
        load_dotenv(env_file)


def _telegram_chat_ids_from_env() -> list[int] | None:
    raw = os.getenv("ZEUS_TELEGRAM_ALLOWED_CHAT_IDS") or os.getenv("TELEGRAM_ALLOWED_USERS") or ""
    if raw:
        return [int(x.strip()) for x in raw.split(",") if x.strip()]
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if chat_id:
        return [int(chat_id.strip())]
    return None


def _start_telegram(poll_interval: float) -> None:
    token = os.getenv("ZEUS_TELEGRAM_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
    allowed_chat_ids = _telegram_chat_ids_from_env()
    if not token or not allowed_chat_ids:
        raise RuntimeError("Telegram gateway is not configured. Run: zeus gateway setup telegram")
    gateway = TelegramGateway(
        token=token,
        allowed_chat_ids=allowed_chat_ids,
        poll_interval=poll_interval,
    )
    gateway.run()


def _start_whatsapp(poll_interval: float, base_url: str) -> None:
    raw_numbers = os.getenv("ZEUS_WHATSAPP_ALLOWED_NUMBERS", "")
    allowed_numbers = [n.strip() for n in raw_numbers.split(",") if n.strip()] if raw_numbers else None
    gateway = WhatsAppGateway(
        base_url=base_url or os.getenv("ZEUS_WHATSAPP_URL", "http://127.0.0.1:9877"),
        allowed_numbers=allowed_numbers,
        poll_interval=poll_interval,
    )
    gateway.run()


def _start_discord() -> None:
    token = os.getenv("ZEUS_DISCORD_TOKEN")
    if not token:
        raise RuntimeError("Discord gateway is not configured. Run: zeus gateway setup discord")
    raw_user_ids = os.getenv("ZEUS_DISCORD_ALLOWED_USER_IDS", "")
    allowed_user_ids = [int(x.strip()) for x in raw_user_ids.split(",") if x.strip()] if raw_user_ids else None
    raw_channel_ids = os.getenv("ZEUS_DISCORD_ALLOWED_CHANNEL_IDS", "")
    allowed_channel_ids = [int(x.strip()) for x in raw_channel_ids.split(",") if x.strip()] if raw_channel_ids else None
    gateway = DiscordGateway(
        token=token,
        allowed_user_ids=allowed_user_ids,
        allowed_channel_ids=allowed_channel_ids,
    )
    gateway.run()


def _ask_service_mode(platform: str) -> str:
    print("\nComo deseja executar o gateway?")
    print("1. manual   - roda no terminal, para com Ctrl+C")
    print("2. systemd  - roda em background e reinicia automaticamente")
    choice = input("Escolha [1/2]: ").strip().lower()
    return "systemd" if choice in ("2", "systemd", "s") else "manual"


def _start_service(platform: str) -> None:
    service_map = {
        "telegram": "zeus-telegram-gateway.service",
        "whatsapp": "zeus-whatsapp-gateway.service",
        "discord": "zeus-discord-gateway.service",
    }
    service = service_map.get(platform)
    if not service:
        raise RuntimeError(f"Unknown platform: {platform}")
    try:
        subprocess.run(["sudo", "systemctl", "restart", service], check=True)
        print(f"Serviço {service} reiniciado.")
        print(f"Logs: journalctl -u {service} -f")
    except subprocess.CalledProcessError as e:
        print(f"Falha ao reiniciar serviço: {e}")
        sys.exit(1)


def main() -> None:
    _load_env()
    parser = argparse.ArgumentParser(description="Zeus Gateway")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Legacy: python -m zeus.gateway --platform telegram
    parser.add_argument("--platform", choices=["telegram", "whatsapp", "discord"], default=None, help=argparse.SUPPRESS)
    parser.add_argument("--token", help=argparse.SUPPRESS)
    parser.add_argument("--allowed-chat-ids", help=argparse.SUPPRESS)
    parser.add_argument("--allowed-numbers", help=argparse.SUPPRESS)
    parser.add_argument("--allowed-user-ids", help=argparse.SUPPRESS)
    parser.add_argument("--allowed-channel-ids", help=argparse.SUPPRESS)
    parser.add_argument("--whatsapp-url", default="http://127.0.0.1:9877", help=argparse.SUPPRESS)
    parser.add_argument("--poll-interval", type=float, default=1.0, help=argparse.SUPPRESS)

    # start command
    start_parser = subparsers.add_parser("start", help="Start a gateway")
    start_parser.add_argument("platform", choices=["telegram", "whatsapp", "discord"])
    start_parser.add_argument("--mode", choices=["manual", "systemd"], default=None)
    start_parser.add_argument("--poll-interval", type=float, default=1.0)
    start_parser.add_argument("--whatsapp-url", default="http://127.0.0.1:9877")

    # setup command
    setup_parser = subparsers.add_parser("setup", help="Configure a gateway interactively")
    setup_parser.add_argument("platform", choices=["telegram", "whatsapp", "discord"])
    setup_parser.add_argument("--token", help="Bot token (Telegram/Discord)")
    setup_parser.add_argument("--chat-id", help="Allowed Telegram chat ID")
    setup_parser.add_argument("--skip-validation", action="store_true", help="Skip Telegram token validation")
    setup_parser.add_argument("--allowed-numbers", help="Allowed WhatsApp numbers (comma-separated)")
    setup_parser.add_argument("--allowed-user-ids", help="Allowed Discord user IDs (comma-separated)")
    setup_parser.add_argument("--allowed-channel-ids", help="Allowed Discord channel IDs (comma-separated)")
    setup_parser.add_argument("--whatsapp-url", default="http://127.0.0.1:9877", help="WhatsApp Baileys bridge URL")

    args = parser.parse_args()

    # Legacy path
    if args.platform and not args.command:
        if args.platform == "telegram":
            os.environ.setdefault("ZEUS_TELEGRAM_TOKEN", args.token or "")
            if args.allowed_chat_ids:
                os.environ.setdefault("ZEUS_TELEGRAM_ALLOWED_CHAT_IDS", args.allowed_chat_ids)
            _start_telegram(args.poll_interval)
        elif args.platform == "whatsapp":
            if args.allowed_numbers:
                os.environ.setdefault("ZEUS_WHATSAPP_ALLOWED_NUMBERS", args.allowed_numbers)
            _start_whatsapp(args.poll_interval, args.whatsapp_url)
        elif args.platform == "discord":
            os.environ.setdefault("ZEUS_DISCORD_TOKEN", args.token or "")
            if args.allowed_user_ids:
                os.environ.setdefault("ZEUS_DISCORD_ALLOWED_USER_IDS", args.allowed_user_ids)
            if args.allowed_channel_ids:
                os.environ.setdefault("ZEUS_DISCORD_ALLOWED_CHANNEL_IDS", args.allowed_channel_ids)
            _start_discord()
        return

    if args.command == "setup":
        if args.platform == "telegram":
            ok = setup_telegram(token=args.token, chat_id=args.chat_id, skip_validation=args.skip_validation)
        elif args.platform == "whatsapp":
            ok = setup_whatsapp(base_url=args.whatsapp_url, allowed_numbers=args.allowed_numbers)
        elif args.platform == "discord":
            ok = setup_discord(
                token=args.token,
                allowed_user_ids=args.allowed_user_ids,
                allowed_channel_ids=args.allowed_channel_ids,
            )
        else:
            parser.error("Platform required")
        sys.exit(0 if ok else 1)

    if args.command == "start":
        if not ensure_configured(args.platform):
            print("Configuração cancelada.")
            sys.exit(1)
        # Reload env after setup may have written new values
        _load_env()

        mode = args.mode or _ask_service_mode(args.platform)
        if mode == "systemd":
            _start_service(args.platform)
            return

        if args.platform == "telegram":
            _start_telegram(args.poll_interval)
        elif args.platform == "whatsapp":
            _start_whatsapp(args.poll_interval, args.whatsapp_url)
        elif args.platform == "discord":
            _start_discord()
        return

    parser.print_help()


if __name__ == "__main__":
    main()
