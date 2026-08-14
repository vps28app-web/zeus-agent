"""CLI for starting the Zeus gateway."""

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv

from zeus.gateway.telegram import TelegramGateway
from zeus.gateway.whatsapp import WhatsAppGateway
from zeus.gateway.discord import DiscordGateway


def _load_env() -> None:
    """Load .env from the project root if present."""
    cwd = Path.cwd()
    env_file = cwd / ".env"
    if env_file.exists():
        load_dotenv(env_file)


def main() -> None:
    _load_env()
    parser = argparse.ArgumentParser(description="Zeus Gateway")
    parser.add_argument("--platform", choices=["telegram", "whatsapp", "discord"], default="telegram", help="Gateway platform")
    parser.add_argument("--token", help="Telegram or Discord bot token")
    parser.add_argument("--allowed-chat-ids", help="Comma-separated allowed Telegram chat IDs")
    parser.add_argument("--allowed-numbers", help="Comma-separated allowed WhatsApp numbers (jid format)")
    parser.add_argument("--allowed-user-ids", help="Comma-separated allowed Discord user IDs")
    parser.add_argument("--allowed-channel-ids", help="Comma-separated allowed Discord channel IDs")
    parser.add_argument("--whatsapp-url", default="http://127.0.0.1:9877", help="WhatsApp Baileys bridge URL")
    parser.add_argument("--poll-interval", type=float, default=1.0, help="Polling interval in seconds (Telegram/WhatsApp)")
    args = parser.parse_args()

    if args.platform == "telegram":
        token = args.token or os.getenv("ZEUS_TELEGRAM_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
        allowed_chat_ids = None
        if args.allowed_chat_ids:
            allowed_chat_ids = [int(x.strip()) for x in args.allowed_chat_ids.split(",") if x.strip()]
        elif os.getenv("ZEUS_TELEGRAM_ALLOWED_CHAT_IDS"):
            allowed_chat_ids = [int(x.strip()) for x in os.getenv("ZEUS_TELEGRAM_ALLOWED_CHAT_IDS", "").split(",") if x.strip()]
        elif os.getenv("TELEGRAM_ALLOWED_USERS"):
            allowed_chat_ids = [int(x.strip()) for x in os.getenv("TELEGRAM_ALLOWED_USERS", "").split(",") if x.strip()]
        elif os.getenv("TELEGRAM_CHAT_ID"):
            allowed_chat_ids = [int(os.getenv("TELEGRAM_CHAT_ID", "").strip())]
        if not token:
            raise RuntimeError("Telegram bot token is required. Use --token, ZEUS_TELEGRAM_TOKEN or TELEGRAM_BOT_TOKEN env var.")
        gateway = TelegramGateway(token=token, allowed_chat_ids=allowed_chat_ids, poll_interval=args.poll_interval)
        gateway.run()
    elif args.platform == "whatsapp":
        allowed_numbers = None
        if args.allowed_numbers:
            allowed_numbers = [x.strip() for x in args.allowed_numbers.split(",") if x.strip()]
        elif os.getenv("ZEUS_WHATSAPP_ALLOWED_NUMBERS"):
            allowed_numbers = [x.strip() for x in os.getenv("ZEUS_WHATSAPP_ALLOWED_NUMBERS", "").split(",") if x.strip()]
        gateway = WhatsAppGateway(
            base_url=args.whatsapp_url,
            allowed_numbers=allowed_numbers,
            poll_interval=args.poll_interval,
        )
        gateway.run()
    elif args.platform == "discord":
        token = args.token or os.getenv("ZEUS_DISCORD_TOKEN")
        allowed_user_ids = None
        if args.allowed_user_ids:
            allowed_user_ids = [int(x.strip()) for x in args.allowed_user_ids.split(",") if x.strip()]
        elif os.getenv("ZEUS_DISCORD_ALLOWED_USER_IDS"):
            allowed_user_ids = [int(x.strip()) for x in os.getenv("ZEUS_DISCORD_ALLOWED_USER_IDS", "").split(",") if x.strip()]
        allowed_channel_ids = None
        if args.allowed_channel_ids:
            allowed_channel_ids = [int(x.strip()) for x in args.allowed_channel_ids.split(",") if x.strip()]
        elif os.getenv("ZEUS_DISCORD_ALLOWED_CHANNEL_IDS"):
            allowed_channel_ids = [int(x.strip()) for x in os.getenv("ZEUS_DISCORD_ALLOWED_CHANNEL_IDS", "").split(",") if x.strip()]
        if not token:
            raise RuntimeError("Discord bot token is required. Use --token or ZEUS_DISCORD_TOKEN env var.")
        gateway = DiscordGateway(
            token=token,
            allowed_user_ids=allowed_user_ids,
            allowed_channel_ids=allowed_channel_ids,
        )
        gateway.run()
    else:
        raise RuntimeError(f"Unsupported platform: {args.platform}")
