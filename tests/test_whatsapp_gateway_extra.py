"""Additional unit tests for zeus/gateway/whatsapp.py."""

from unittest.mock import patch

from zeus.gateway.whatsapp import WhatsAppGateway


def test_handle_message_pending_input():
    gw = WhatsAppGateway(allowed_numbers=["123@s.whatsapp.net"])
    gw._pending_inputs["123@s.whatsapp.net"] = "original question"

    with patch.object(gw, "connection", return_value="connected"):
        with patch("zeus.gateway.whatsapp.run_agent", return_value="answered") as mock_run:
            with patch.object(gw, "send_message"):
                gw.handle_message({"from": "123@s.whatsapp.net", "text": "yes", "timestamp": 1})

    call_args = mock_run.call_args[0][0]
    assert "original question" in call_args
    assert "Confirmação" in call_args


def test_handle_message_logs_error():
    gw = WhatsAppGateway(allowed_numbers=["123@s.whatsapp.net"])

    with patch.object(gw, "connection", return_value="connected"):
        with patch("zeus.gateway.whatsapp.run_agent", side_effect=RuntimeError("fail")):
            with patch.object(gw, "send_message") as mock_send:
                gw.handle_message({"from": "123@s.whatsapp.net", "text": "hi", "timestamp": 1})

    assert mock_send.call_count == 1


def test_run_polls_messages_and_stops():
    gw = WhatsAppGateway(allowed_numbers=["123@s.whatsapp.net"], poll_interval=0.01)

    calls = {"count": 0}

    def fake_get_messages():
        calls["count"] += 1
        if calls["count"] >= 2:
            gw.running = False
        return []

    with patch.object(gw, "get_messages", fake_get_messages):
        with patch("time.sleep"):
            gw.run()

    assert gw.running is False


def test_run_keyboard_interrupt():
    gw = WhatsAppGateway(allowed_numbers=["123@s.whatsapp.net"])

    def raise_interrupt():
        raise KeyboardInterrupt()

    with patch.object(gw, "get_messages", side_effect=raise_interrupt):
        gw.run()

    assert gw.running is False
