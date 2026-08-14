"""Entry point for Zeus gateway."""

import os

from zeus.gateway.telegram import start_from_env as start_telegram
from zeus.gateway.whatsapp import start_from_env as start_whatsapp
from zeus.gateway.discord import start_from_env as start_discord

if __name__ == "__main__":
    platform = os.getenv("ZEUS_GATEWAY_PLATFORM", "telegram").lower()
    if platform == "whatsapp":
        start_whatsapp()
    elif platform == "discord":
        start_discord()
    else:
        start_telegram()
