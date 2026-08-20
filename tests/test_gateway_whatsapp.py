"""Tests for the WhatsApp gateway."""

from unittest.mock import MagicMock, patch

from zeus.gateway.whatsapp import WhatsAppGateway


class TestWhatsAppGateway:
    def test_chunk_text(self):
        assert WhatsAppGateway._chunk_text("hello") == ["hello"]
        text = "x" * 5000
        chunks = WhatsAppGateway._chunk_text(text, max_length=4000)
        assert len(chunks) == 2

    def test_is_allowed_empty(self):
        gateway = WhatsAppGateway(allowed_numbers=[])
        assert not gateway.is_allowed("5511999999999@s.whatsapp.net")

    def test_is_allowed_match(self):
        gateway = WhatsAppGateway(allowed_numbers=["5511999999999@s.whatsapp.net"])
        assert gateway.is_allowed("5511999999999@s.whatsapp.net")

    @patch("zeus.gateway.whatsapp.run_agent")
    @patch("zeus.gateway.whatsapp.requests.get")
    @patch("zeus.gateway.whatsapp.requests.post")
    def test_handle_message_skips_when_disconnected(self, mock_post, mock_get, mock_run_agent):
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"connection": "disconnected"}
        mock_get.return_value = mock_response

        gateway = WhatsAppGateway(allowed_numbers=["5511999999999@s.whatsapp.net"])
        gateway.handle_message({
            "from": "5511999999999@s.whatsapp.net",
            "text": "hello",
            "timestamp": 123,
        })
        mock_run_agent.assert_not_called()
        mock_post.assert_not_called()

    @patch("zeus.gateway.whatsapp.run_agent")
    @patch("zeus.gateway.whatsapp.requests.get")
    @patch("zeus.gateway.whatsapp.requests.post")
    def test_handle_message_processes_when_connected(self, mock_post, mock_get, mock_run_agent):
        def json_side_effect():
            if mock_get.call_args[0][0].endswith("/connection"):
                return {"connection": "connected"}
            return {"messages": []}

        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.side_effect = json_side_effect
        mock_get.return_value = mock_response

        mock_send_response = MagicMock()
        mock_send_response.raise_for_status.return_value = None
        mock_send_response.json.return_value = {"sent": True}
        mock_post.return_value = mock_send_response

        mock_run_agent.return_value = "Hello back"

        gateway = WhatsAppGateway(allowed_numbers=["5511999999999@s.whatsapp.net"])
        gateway.handle_message({
            "from": "5511999999999@s.whatsapp.net",
            "text": "hello",
            "timestamp": 123,
        })

        mock_run_agent.assert_called_once()
        mock_post.assert_called_once()
        assert mock_post.call_args.kwargs["json"]["to"] == "5511999999999@s.whatsapp.net"
        assert mock_post.call_args.kwargs["json"]["text"] == "Hello back"
