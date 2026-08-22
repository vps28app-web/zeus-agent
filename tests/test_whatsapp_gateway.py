"""Unit tests for zeus/gateway/whatsapp.py."""

from unittest.mock import patch

from zeus.gateway.whatsapp import WhatsAppGateway, start_from_env


def test_chunk_text_short():
    assert WhatsAppGateway._chunk_text("hello") == ["hello"]


def test_chunk_text_long():
    text = "a" * 9000
    chunks = WhatsAppGateway._chunk_text(text, max_length=4000)
    assert len(chunks) == 3
    assert len(chunks[0]) == 4000


def test_is_allowed_with_empty_list():
    gw = WhatsAppGateway(allowed_numbers=[])
    assert gw.is_allowed("123@s.whatsapp.net") is False


def test_is_allowed_with_numbers():
    gw = WhatsAppGateway(allowed_numbers=["123@s.whatsapp.net"])
    assert gw.is_allowed("123@s.whatsapp.net") is True
    assert gw.is_allowed("999@s.whatsapp.net") is False


def test_health():
    gw = WhatsAppGateway()
    with patch.object(gw, "_get", return_value={"status": "ok"}):
        assert gw.health()["status"] == "ok"


def test_connection_connected():
    gw = WhatsAppGateway()
    with patch.object(gw, "_get", return_value={"connection": "connected"}):
        assert gw.connection() == "connected"


def test_connection_unreachable():
    gw = WhatsAppGateway()
    with patch.object(gw, "_get", side_effect=Exception("down")):
        assert gw.connection() == "unreachable"


def test_get_messages():
    gw = WhatsAppGateway()
    with patch.object(gw, "_get", return_value={"messages": [{"from": "x", "text": "hi"}]}):
        msgs = gw.get_messages()
    assert len(msgs) == 1


def test_send_message_chunks():
    gw = WhatsAppGateway()
    with patch.object(gw, "_post") as mock_post:
        gw.send_message("123@s.whatsapp.net", "hello")
    mock_post.assert_called_once_with("/send", {"to": "123@s.whatsapp.net", "text": "hello"})


def test_handle_message_ignores_empty():
    gw = WhatsAppGateway(allowed_numbers=["123@s.whatsapp.net"])
    with patch.object(gw, "send_message") as mock_send:
        gw.handle_message({"from": "123@s.whatsapp.net", "text": "   "})
    mock_send.assert_not_called()


def test_handle_message_ignores_unauthorized():
    gw = WhatsAppGateway(allowed_numbers=["123@s.whatsapp.net"])
    with patch.object(gw, "send_message") as mock_send:
        gw.handle_message({"from": "999@s.whatsapp.net", "text": "hi"})
    mock_send.assert_not_called()


def test_handle_message_when_not_connected():
    gw = WhatsAppGateway(allowed_numbers=["123@s.whatsapp.net"])
    with patch.object(gw, "connection", return_value="disconnected"):
        with patch.object(gw, "send_message") as mock_send:
            gw.handle_message({"from": "123@s.whatsapp.net", "text": "hi"})
    mock_send.assert_not_called()


def test_handle_message_runs_agent_and_replies():
    gw = WhatsAppGateway(allowed_numbers=["123@s.whatsapp.net"])

    with patch.object(gw, "connection", return_value="connected"):
        with patch("zeus.gateway.whatsapp.run_agent", return_value="hello back") as mock_run:
            with patch.object(gw, "send_message") as mock_send:
                gw.handle_message({"from": "123@s.whatsapp.net", "text": "hi", "timestamp": 1})

    mock_run.assert_called_once()
    mock_send.assert_called_once_with("123@s.whatsapp.net", "hello back")


def test_handle_message_permission_required():
    gw = WhatsAppGateway(allowed_numbers=["123@s.whatsapp.net"])

    response = {"permission_required": {"action": "write", "path": "/tmp/x.txt"}}

    with patch.object(gw, "connection", return_value="connected"):
        with patch("zeus.gateway.whatsapp.run_agent", return_value=response):
            with patch.object(gw, "send_message") as mock_send:
                with patch.object(gw._confirmations, "request") as mock_request:
                    gw.handle_message({"from": "123@s.whatsapp.net", "text": "delete file", "timestamp": 1})

    mock_send.assert_called_once()
    mock_request.assert_called_once()


def test_handle_message_agent_error():
    gw = WhatsAppGateway(allowed_numbers=["123@s.whatsapp.net"])

    with patch.object(gw, "connection", return_value="connected"):
        with patch("zeus.gateway.whatsapp.run_agent", side_effect=RuntimeError("boom")):
            with patch.object(gw, "send_message") as mock_send:
                gw.handle_message({"from": "123@s.whatsapp.net", "text": "hi", "timestamp": 1})

    assert mock_send.call_count == 1
    assert "Erro" in mock_send.call_args[0][1]


def test_confirmation_answer_handles_response():
    gw = WhatsAppGateway(allowed_numbers=["123@s.whatsapp.net"])
    called = {"choice": None}

    def on_response(choice):
        called["choice"] = choice

    gw._confirmations.request("whatsapp", "123@s.whatsapp.net", "write", "/tmp/x", on_response)
    result = gw._confirmations.answer("whatsapp", "123@s.whatsapp.net", "yes")

    assert result is True
    assert called["choice"] == "once"


def test_resume_after_confirmation_denied():
    gw = WhatsAppGateway(allowed_numbers=["123@s.whatsapp.net"])
    with patch.object(gw, "send_message") as mock_send:
        gw._resume_after_confirmation("delete", "deny", "123@s.whatsapp.net", "sid", "user")
    mock_send.assert_called_once_with("123@s.whatsapp.net", "Ação negada pelo usuário / Action denied by user.")


def test_resume_after_confirmation_runs_worker():
    gw = WhatsAppGateway(allowed_numbers=["123@s.whatsapp.net"])

    with patch("zeus.gateway.whatsapp.run_agent", return_value="done") as mock_run:
        with patch.object(gw, "_post"):
            gw._resume_after_confirmation("read file", "once", "123@s.whatsapp.net", "sid", "user")
            import time
            time.sleep(0.3)

    mock_run.assert_called_once()


def test_stop():
    gw = WhatsAppGateway()
    gw.running = True
    gw.stop()
    assert gw.running is False


def test_start_from_env():
    with patch.dict("os.environ", {"ZEUS_WHATSAPP_ALLOWED_NUMBERS": "123@s.whatsapp.net"}, clear=False):
        with patch.object(WhatsAppGateway, "run") as mock_run:
            start_from_env()
    mock_run.assert_called_once()
