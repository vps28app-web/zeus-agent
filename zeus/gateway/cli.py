"""CLI for starting the Zeus gateway."""

import argparse

from zeus.gateway.telegram import TelegramGateway
from zeus.gateway.whatsapp import WhatsAppGateway
from zeus.gateway.discord import DiscordGateway


def main() -> None:
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
        token = args.token
        allowed_chat_ids = None
        if args.allowed_chat_ids:
            allowed_chat_ids = [int(x.strip()) for x in args.allowed_chat_ids.split(",") if x.strip()]
        if not token:
            raise RuntimeError("Telegram bot token is required. Use --token or ZEUS_TELEGRAM_TOKEN env var.")
        gateway = TelegramGateway(token=token, allowed_chat_ids=allowed_chat_ids, poll_interval=args.poll_interval)
        gateway.run()
    elif args.platform == "whatsapp":
        allowed_numbers = None
        if args.allowed_numbers:
            allowed_numbers = [x.strip() for x in args.allowed_numbers.split(",") if x.strip()]
        gateway = WhatsAppGateway(
            base_url=args.whatsapp_url,
            allowed_numbers=allowed_numbers,
            poll_interval=args.poll_interval,
        )
        gateway.run()
    elif args.platform == "discord":
        token = args.token
        allowed_user_ids = None
        if args.allowed_user_ids:
            allowed_user_ids = [int(x.strip()) for x in args.allowed_user_ids.split(",") if x.strip()]
        allowed_channel_ids = None
        if args.allowed_channel_ids:
            allowed_channel_ids = [int(x.strip()) for x in args.allowed_channel_ids.split(",") if x.strip()]
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
