"""Tests for Instagram Messaging setup and webhook gateway."""

from zeus.gateway import setup as gateway_setup


def test_setup_instagram_saves_required_settings_masked(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ZEUS_HOME", str(tmp_path))
    answers = iter(
        [
            "1234567890",
            "access-token-secret",
            "meta-app-secret",
            "verify-token-secret",
            "https://bot.example/webhook",
        ]
    )
    prompts = []

    def fake_input(prompt, default=None, secret=False):
        prompts.append((prompt, secret))
        return next(answers)

    monkeypatch.setattr(gateway_setup, "_get_input", fake_input)

    assert gateway_setup.setup_instagram() is True

    saved = (tmp_path / ".env").read_text()
    assert (tmp_path / ".env").stat().st_mode & 0o077 == 0
    assert "ZEUS_INSTAGRAM_ACCOUNT_ID=1234567890" in saved
    assert "ZEUS_INSTAGRAM_ACCESS_TOKEN=access-token-secret" in saved
    assert "ZEUS_INSTAGRAM_APP_SECRET=meta-app-secret" in saved
    assert "ZEUS_INSTAGRAM_VERIFY_TOKEN=verify-token-secret" in saved
    assert "ZEUS_INSTAGRAM_PUBLIC_WEBHOOK_URL=https://bot.example/webhook" in saved
    assert [secret for _, secret in prompts] == [False, True, True, True, False]
    output = capsys.readouterr().out
    assert "access-token-secret" not in output
    assert "meta-app-secret" not in output


def test_instagram_signature_matches_meta_hmac():
    import hashlib
    import hmac

    from zeus.gateway.instagram import InstagramGateway

    body = b'{"entry":[]}'
    digest = hmac.new(b"test-app-secret", body, hashlib.sha256).hexdigest()
    assert InstagramGateway.verify_signature(body, f"sha256={digest}", "test-app-secret")
    assert not InstagramGateway.verify_signature(body, "sha256=bad", "test-app-secret")


def test_instagram_chunks_utf8_by_byte_limit():
    from zeus.gateway.instagram import InstagramGateway

    chunks = InstagramGateway._chunks("😀" * 400)
    assert all(len(chunk.encode("utf-8")) <= 1000 for chunk in chunks)
    assert "".join(chunks) == "😀" * 400


def test_instagram_processes_text_dm_and_replies(monkeypatch):
    from unittest.mock import MagicMock, patch

    from zeus.gateway.instagram import InstagramGateway

    gateway = InstagramGateway("access", "account", "secret", "verify")
    logger = MagicMock()
    monkeypatch.setattr("zeus.gateway.instagram.get_logger", lambda session_id: logger)
    with patch("zeus.gateway.instagram.run_agent", return_value="Zeus online") as run_agent:
        with patch.object(gateway, "send_message") as send:
            gateway.process_payload(
                {
                    "entry": [
                        {
                            "id": "account",
                            "messaging": [
                                {
                                    "sender": {"id": "customer"},
                                    "message": {"mid": "m1", "text": "oi"},
                                }
                            ],
                        }
                    ]
                }
            )

    run_agent.assert_called_once()
    send.assert_called_once_with("customer", "Zeus online")


def test_instagram_webhook_verify_challenge():
    import threading

    import requests

    from zeus.gateway.instagram import InstagramGateway

    gateway = InstagramGateway("access", "account", "secret", "verify", port=0)
    server = gateway.make_server()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        response = requests.get(
            f"http://127.0.0.1:{port}/webhook",
            params={"hub.mode": "subscribe", "hub.verify_token": "verify", "hub.challenge": "12345"},
            timeout=3,
        )
        assert response.status_code == 200
        assert response.text == "12345"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_instagram_webhook_rejects_bad_signature():
    import threading

    import requests

    from zeus.gateway.instagram import InstagramGateway

    gateway = InstagramGateway("access", "account", "secret", "verify", port=0)
    server = gateway.make_server()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        response = requests.post(
            f"http://127.0.0.1:{server.server_address[1]}/webhook",
            data=b'{"entry":[]}',
            headers={"X-Hub-Signature-256": "sha256=invalid"},
            timeout=3,
        )
        assert response.status_code == 401
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_instagram_webhook_accepts_signed_event():
    import hashlib
    import hmac
    import threading
    from unittest.mock import patch

    import requests

    from zeus.gateway.instagram import InstagramGateway

    body = b'{"entry":[]}'
    signature = hmac.new(b"secret", body, hashlib.sha256).hexdigest()
    gateway = InstagramGateway("access", "account", "secret", "verify", port=0)
    server = gateway.make_server()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        called = threading.Event()
        received_payloads = []

        def record_payload(payload):
            received_payloads.append(payload)
            called.set()

        with patch.object(gateway, "process_payload", side_effect=record_payload):
            response = requests.post(
                f"http://127.0.0.1:{server.server_address[1]}/webhook",
                data=body,
                headers={"X-Hub-Signature-256": f"sha256={signature}"},
                timeout=3,
            )
            assert response.status_code == 200
            assert called.wait(timeout=3)
            assert received_payloads == [{"entry": []}]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
