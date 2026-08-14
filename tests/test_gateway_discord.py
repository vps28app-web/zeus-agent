"""Tests for the Discord gateway."""

from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from zeus.gateway.discord import DiscordClient, DiscordGateway


def _make_message(content: str, *, user_id: int = 123, channel_id: int = 456, guild=None, bot=False, mention=True):
    message = MagicMock(spec=discord.Message)
    message.content = content
    message.author = MagicMock()
    message.author.id = user_id
    message.author.bot = bot
    message.author.__str__ = lambda self: "user#1234"
    message.channel = MagicMock()
    message.channel.id = channel_id
    message.channel.send = AsyncMock()
    message.guild = guild
    message.mentions = []
    return message


class TestDiscordClientChunk:
    def test_chunk_text_short(self):
        assert DiscordClient._chunk_text("hello") == ["hello"]

    def test_chunk_text_long_splits_on_newline(self):
        text = "line\n" * 1000
        chunks = DiscordClient._chunk_text(text, max_length=50)
        assert all(len(c) <= 50 for c in chunks)


class TestDiscordClientOnMessage:
    @pytest.mark.asyncio
    async def test_ignores_own_messages(self):
        client = DiscordClient()
        client._connection.user = MagicMock()
        client._connection.user.id = 999
        message = _make_message("hello", user_id=999)
        message.author = client._connection.user
        await client.on_message(message)
        message.channel.send.assert_not_called()

    @pytest.mark.asyncio
    async def test_ignores_unauthorized_user(self):
        client = DiscordClient(allowed_user_ids={111})
        client._connection.user = MagicMock()
        client._connection.user.id = 999
        message = _make_message("hello", user_id=123)
        await client.on_message(message)
        message.channel.send.assert_not_called()

    @pytest.mark.asyncio
    async def test_ignores_guild_without_mention(self):
        client = DiscordClient(allowed_user_ids={123})
        client._connection.user = MagicMock()
        client._connection.user.id = 999
        client._connection.user.mentioned_in = lambda m: False
        guild = MagicMock()
        message = _make_message("hello", user_id=123, guild=guild)
        await client.on_message(message)
        message.channel.send.assert_not_called()

    @pytest.mark.asyncio
    @patch("zeus.gateway.discord.run_agent")
    async def test_responds_to_dm(self, mock_run_agent):
        client = DiscordClient(allowed_user_ids={123})
        client._connection.user = MagicMock()
        client._connection.user.id = 999
        client._connection.user.mentioned_in = lambda m: False
        mock_run_agent.return_value = "Hello from Zeus"
        message = _make_message("hello", user_id=123)
        await client.on_message(message)
        message.channel.send.assert_called_once_with("Hello from Zeus")


class TestDiscordGateway:
    @patch("zeus.gateway.discord.discord.Client.run")
    def test_run(self, mock_run):
        gateway = DiscordGateway(token="secret", allowed_user_ids=[123])
        gateway.run()
        mock_run.assert_called_once_with("secret")
