"""Gateway tests ensuring !zeus is handled without an LLM call."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from zeus.gateway.discord import DiscordClient
from zeus.gateway.telegram import TelegramGateway
from zeus.gateway.whatsapp import WhatsAppGateway


def test_telegram_handles_zeus_command_locally():
    gateway = TelegramGateway(token="x", allowed_chat_ids=[123])
    update = {
        "update_id": 1,
        "message": {
            "message_id": 1,
            "chat": {"id": 123, "username": "alice"},
            "text": "!zeus",
        },
    }
    with patch.object(gateway, "send_message") as send:
        with patch("zeus.gateway.telegram._run_agent_with_timeout") as run_agent:
            gateway.handle_update(update)

    run_agent.assert_not_called()
    assert "!zeus status" in send.call_args.args[1]


def test_whatsapp_handles_zeus_command_locally():
    gateway = WhatsAppGateway(allowed_numbers=["123@s.whatsapp.net"])
    message = {"from": "123@s.whatsapp.net", "text": "!zeus status"}
    with patch.object(gateway, "connection", return_value="connected"):
        with patch.object(gateway, "send_message") as send:
            with patch("zeus.gateway.whatsapp.run_agent") as run_agent:
                gateway.handle_message(message)

    run_agent.assert_not_called()
    assert "Provedor:" in send.call_args.args[1]


@pytest.mark.asyncio
async def test_discord_handles_zeus_command_locally():
    client = DiscordClient(allowed_user_ids={123})
    client._connection.user = MagicMock()
    client._connection.user.id = 999
    client._connection.user.mentioned_in = lambda message: False
    message = MagicMock()
    message.author = MagicMock(id=123, bot=False)
    message.author.__str__ = lambda self: "user#1234"
    message.channel = MagicMock(id=456)
    message.channel.send = AsyncMock()
    message.guild = None
    message.content = "!zeus setup"

    with patch("zeus.gateway.discord.run_agent") as run_agent:
        await client.on_message(message)

    run_agent.assert_not_called()
    message.channel.send.assert_awaited_once()
    assert "zeus setup" in message.channel.send.call_args.args[0]
