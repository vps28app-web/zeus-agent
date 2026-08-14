"""Discord bot gateway for Zeus.

Uses discord.py to listen to direct messages and guild mentions.
"""

import asyncio
import os
from typing import List, Optional, Set

import discord

from zeus.core.agent import run_agent
from zeus.memory.session_log import get_logger


class DiscordClient(discord.Client):
    def __init__(
        self,
        allowed_user_ids: Optional[Set[int]] = None,
        allowed_channel_ids: Optional[Set[int]] = None,
        **kwargs,
    ):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.dm_messages = True
        super().__init__(intents=intents, **kwargs)
        self.allowed_user_ids = allowed_user_ids or set()
        self.allowed_channel_ids = allowed_channel_ids or set()

    async def on_ready(self) -> None:
        print(f"Discord gateway logged in as {self.user}")

    async def on_message(self, message: discord.Message) -> None:
        if message.author == self.user:
            return

        # Ignore bot messages unless explicitly allowed.
        if message.author.bot:
            return

        text = message.content.strip()
        if not text:
            return

        # In guilds, only respond to mentions.
        if message.guild and self.user and not self.user.mentioned_in(message):
            return

        # Strip mention prefix from guild messages.
        if message.guild and self.user:
            text = text.replace(f"<@{self.user.id}>", "").replace(f"<@!{self.user.id}>", "").strip()
            if not text:
                return

        user_id = message.author.id
        channel_id = message.channel.id

        if self.allowed_user_ids and user_id not in self.allowed_user_ids:
            print(f"Ignoring message from unauthorized user: {user_id}")
            return
        if self.allowed_channel_ids and channel_id not in self.allowed_channel_ids:
            print(f"Ignoring message from unauthorized channel: {channel_id}")
            return

        print(f"Discord message from {message.author} ({user_id}): {text[:80]}")
        session_id = f"discord-{user_id}-{channel_id}"
        logger = get_logger(session_id)
        logger.log_turn(
            "user",
            text,
            metadata={
                "user_id": user_id,
                "channel_id": channel_id,
                "username": str(message.author),
                "platform": "discord",
            },
        )

        try:
            response = run_agent(text, session_id=logger.session_id)
            logger.log_turn("assistant", response, metadata={"platform": "discord"})
            await self._send_chunks(message.channel, response)
        except Exception as e:
            logger.log_turn("error", str(e), metadata={"platform": "discord"})
            print(f"Error handling Discord message: {e}")
            await message.channel.send(f"Erro: {e}")

    async def _send_chunks(self, channel: discord.abc.Messageable, text: str) -> None:
        chunks = self._chunk_text(text)
        for chunk in chunks:
            await channel.send(chunk)

    @staticmethod
    def _chunk_text(text: str, max_length: int = 2000) -> List[str]:
        if len(text) <= max_length:
            return [text]
        chunks = []
        while text:
            if len(text) <= max_length:
                chunks.append(text)
                break
            split_at = text.rfind("\n", 0, max_length)
            if split_at == -1:
                split_at = max_length
            chunks.append(text[:split_at])
            text = text[split_at:].lstrip()
        return chunks


class DiscordGateway:
    """Gateway wrapper around the Discord client."""

    def __init__(
        self,
        token: str,
        allowed_user_ids: Optional[List[int]] = None,
        allowed_channel_ids: Optional[List[int]] = None,
    ):
        self.token = token
        self.client = DiscordClient(
            allowed_user_ids=set(allowed_user_ids or []),
            allowed_channel_ids=set(allowed_channel_ids or []),
        )

    def run(self) -> None:
        self.client.run(self.token)

    def stop(self) -> None:
        asyncio.create_task(self.client.close())


def start_from_env() -> None:
    """Start Discord gateway using environment variables."""
    token = os.getenv("ZEUS_DISCORD_TOKEN")
    if not token:
        raise RuntimeError("ZEUS_DISCORD_TOKEN not set")

    raw_user_ids = os.getenv("ZEUS_DISCORD_ALLOWED_USER_IDS", "")
    allowed_user_ids = []
    if raw_user_ids:
        allowed_user_ids = [int(x.strip()) for x in raw_user_ids.split(",") if x.strip()]

    raw_channel_ids = os.getenv("ZEUS_DISCORD_ALLOWED_CHANNEL_IDS", "")
    allowed_channel_ids = []
    if raw_channel_ids:
        allowed_channel_ids = [int(x.strip()) for x in raw_channel_ids.split(",") if x.strip()]

    gateway = DiscordGateway(
        token=token,
        allowed_user_ids=allowed_user_ids,
        allowed_channel_ids=allowed_channel_ids,
    )
    gateway.run()
