"""Tests for the Telegram gateway."""

import json
from unittest.mock import MagicMock, patch

import pytest

from zeus.gateway.telegram import TelegramGateway, _escape_html


class TestEscapeHtml:
    def test_escapes_ampersand(self):
        assert _escape_html("a & b") == "a &amp; b"

    def test_escapes_lt_gt(self):
        assert _escape_html("<b>hi</b>") == "&lt;b&gt;hi&lt;/b&gt;"


class TestTelegramGateway:
    def test_chunk_text_short(self):
        assert TelegramGateway._chunk_text("hello") == ["hello"]

    def test_chunk_text_long(self):
        text = "x" * 5000
        chunks = TelegramGateway._chunk_text(text, max_length=4000)
        assert len(chunks) == 2
        assert len(chunks[0]) == 4000
        assert len(chunks[1]) == 1000

    def test_is_allowed_empty(self):
        gateway = TelegramGateway(token="x", allowed_chat_ids=[])
        assert not gateway.is_allowed(123)

    def test_is_allowed_match(self):
        gateway = TelegramGateway(token="x", allowed_chat_ids=[123, 456])
        assert gateway.is_allowed(123)
        assert not gateway.is_allowed(789)

    @patch("zeus.gateway.telegram.requests.post")
    def test_send_message_escapes_html(self, mock_post):
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"ok": True}
        mock_post.return_value = mock_response

        gateway = TelegramGateway(token="x", allowed_chat_ids=[1])
        gateway.send_message(1, "<script>alert(1)</script>")

        call = mock_post.call_args
        payload = json.loads(json.dumps(call.kwargs["json"]))
        assert payload["text"] == "&lt;script&gt;alert(1)&lt;/script&gt;"
        assert payload["parse_mode"] == "HTML"

    @patch("zeus.gateway.telegram.run_agent")
    @patch("zeus.gateway.telegram.requests.post")
    def test_handle_update_ignores_unauthorized(self, mock_post, mock_run_agent):
        gateway = TelegramGateway(token="x", allowed_chat_ids=[999])
        update = {
            "update_id": 1,
            "message": {
                "message_id": 1,
                "chat": {"id": 123, "username": "alice"},
                "text": "hello",
            },
        }
        gateway.handle_update(update)
        mock_run_agent.assert_not_called()
        mock_post.assert_not_called()

    @patch("zeus.gateway.telegram._run_agent_with_timeout")
    @patch("zeus.gateway.telegram.requests.post")
    def test_handle_update_timeout(self, mock_post, mock_run_agent):
        mock_run_agent.side_effect = TimeoutError("Agent took longer than 120s")
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"ok": True}
        mock_post.return_value = mock_response

        gateway = TelegramGateway(token="x", allowed_chat_ids=[123])
        update = {
            "update_id": 1,
            "message": {
                "message_id": 1,
                "chat": {"id": 123, "username": "alice"},
                "text": "hello",
            },
        }
        gateway.handle_update(update)
        for t in gateway._worker_threads:
            t.join(timeout=2)

        assert mock_post.call_count >= 1
        texts = [call.kwargs["json"].get("text", "") for call in mock_post.call_args_list if "json" in call.kwargs]
        assert any("Demorou muito" in t for t in texts)

    @patch("zeus.gateway.telegram._run_agent_with_timeout")
    @patch("zeus.gateway.telegram.requests.post")
    def test_handle_update_permission_required(self, mock_post, mock_run_agent):
        mock_run_agent.return_value = {
            "permission_required": {"action": "write", "path": "/tmp/test.txt"},
            "pending_input": "write to /tmp/test.txt",
        }
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"ok": True}
        mock_post.return_value = mock_response

        gateway = TelegramGateway(token="x", allowed_chat_ids=[123])
        update = {
            "update_id": 1,
            "message": {
                "message_id": 1,
                "chat": {"id": 123, "username": "alice"},
                "text": "write to /tmp/test.txt",
            },
        }
        gateway.handle_update(update)
        for t in gateway._worker_threads:
            t.join(timeout=2)

        assert gateway._confirmations.has_pending("telegram", "123")
        payload = mock_post.call_args.kwargs["json"]
        assert "Permissão de arquivo necessária: write em '/tmp/test.txt'" in payload["text"]

