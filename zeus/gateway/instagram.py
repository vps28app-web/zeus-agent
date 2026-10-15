"""Webhook gateway for the official Instagram Messaging API."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import parse_qs, urlparse

import requests

from zeus.core.agent import run_agent
from zeus.memory.session_log import get_logger


class InstagramGateway:
    """Receive Instagram DM webhooks and send text replies via Meta's API."""

    def __init__(
        self,
        access_token: str,
        account_id: str,
        app_secret: str,
        verify_token: str,
        host: str = "127.0.0.1",
        port: int = 8765,
        api_version: str = "v26.0",
        allowed_user_ids: Optional[Iterable[str]] = None,
    ):
        self.access_token = access_token
        self.account_id = account_id
        self.app_secret = app_secret
        self.verify_token = verify_token
        self.host = host
        self.port = int(port)
        self.api_version = api_version
        self.allowed_user_ids = set(allowed_user_ids or [])
        self._seen_ids: set[str] = set()
        self._seen_lock = threading.Lock()
        self._server: Optional[ThreadingHTTPServer] = None

    @staticmethod
    def verify_signature(body: bytes, signature: str, app_secret: str) -> bool:
        """Validate Meta's X-Hub-Signature-256 request signature."""
        prefix = "sha256="
        if not signature.startswith(prefix):
            return False
        expected = hmac.new(app_secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(signature[len(prefix):], expected)

    @staticmethod
    def _chunks(text: str, max_bytes: int = 1000) -> List[str]:
        chunks: List[str] = []
        current = ""
        for char in text:
            if current and len((current + char).encode("utf-8")) > max_bytes:
                chunks.append(current)
                current = char
            else:
                current += char
        if current or not chunks:
            chunks.append(current)
        return chunks

    def send_message(self, recipient_id: str, text: str) -> None:
        """Send text to an Instagram-scoped user ID, within Meta's reply window."""
        url = f"https://graph.instagram.com/{self.api_version}/{self.account_id}/messages"
        for chunk in self._chunks(text):
            response = requests.post(
                url,
                headers={"Authorization": f"Bearer {self.access_token}"},
                json={"recipient": {"id": recipient_id}, "message": {"text": chunk}},
                timeout=20,
            )
            response.raise_for_status()

    def _claim_message(self, message_id: str) -> bool:
        if not message_id:
            return True
        with self._seen_lock:
            if message_id in self._seen_ids:
                return False
            self._seen_ids.add(message_id)
            if len(self._seen_ids) > 2000:
                self._seen_ids.clear()
                self._seen_ids.add(message_id)
            return True

    def process_payload(self, payload: Dict[str, Any]) -> None:
        """Dispatch inbound plain-text DM events to the agent."""
        for entry in payload.get("entry", []):
            if entry.get("id") and str(entry["id"]) != self.account_id:
                continue
            for event in entry.get("messaging", []):
                sender_id = str(event.get("sender", {}).get("id", ""))
                message = event.get("message") or {}
                message_id = str(message.get("mid", ""))
                text = message.get("text", "")
                if (
                    not sender_id
                    or sender_id == self.account_id
                    or message.get("is_echo")
                    or not isinstance(text, str)
                    or not text.strip()
                    or not self._claim_message(message_id)
                    or (self.allowed_user_ids and sender_id not in self.allowed_user_ids)
                ):
                    continue

                session_id = f"instagram-{sender_id}"
                logger = get_logger(session_id)
                logger.log_turn("user", text, metadata={"platform": "instagram", "user_id": sender_id})
                try:
                    response = run_agent(
                        text,
                        session_id=logger.session_id,
                        user_id=sender_id,
                        platform="instagram",
                    )
                    if isinstance(response, dict):
                        if response.get("permission_required"):
                            response = "Essa solicitação exige confirmação de segurança; use uma sessão local do Zeus."
                        else:
                            response = str(response)
                    logger.log_turn("assistant", response, metadata={"platform": "instagram", "user_id": sender_id})
                    self.send_message(sender_id, str(response))
                except Exception as exc:
                    logger.log_turn("error", str(exc), metadata={"platform": "instagram"})
                    print(f"Instagram gateway message failed ({type(exc).__name__}).")

    def _make_handler(self):
        gateway = self

        class Handler(BaseHTTPRequestHandler):
            def _reply(self, status: int, body: bytes = b"") -> None:
                self.send_response(status)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                if body:
                    self.wfile.write(body)

            def do_GET(self) -> None:
                parsed = urlparse(self.path)
                if parsed.path != "/webhook":
                    self._reply(404)
                    return
                query = parse_qs(parsed.query)
                mode = query.get("hub.mode", [""])[0]
                token = query.get("hub.verify_token", [""])[0]
                challenge = query.get("hub.challenge", [""])[0]
                if mode == "subscribe" and hmac.compare_digest(token, gateway.verify_token):
                    self._reply(200, challenge.encode("utf-8"))
                else:
                    self._reply(403)

            def do_POST(self) -> None:
                parsed = urlparse(self.path)
                if parsed.path != "/webhook":
                    self._reply(404)
                    return
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                except ValueError:
                    self._reply(400)
                    return
                if length <= 0 or length > 1_000_000:
                    self._reply(413 if length > 1_000_000 else 400)
                    return
                body = self.rfile.read(length)
                signature = self.headers.get("X-Hub-Signature-256", "")
                if not gateway.verify_signature(body, signature, gateway.app_secret):
                    self._reply(401)
                    return
                try:
                    payload = json.loads(body.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    self._reply(400)
                    return
                self._reply(200, b"EVENT_RECEIVED")
                threading.Thread(target=gateway.process_payload, args=(payload,), daemon=True).start()

            def log_message(self, fmt: str, *args: Any) -> None:
                # Avoid logging webhook query strings, which include the verify token.
                return

        return Handler

    def make_server(self) -> ThreadingHTTPServer:
        """Create the local webhook server; expose it through an HTTPS reverse proxy/tunnel."""
        return ThreadingHTTPServer((self.host, self.port), self._make_handler())

    def run(self) -> None:
        server = self.make_server()
        self._server = server
        print(f"Instagram webhook listening on {self.host}:{self.port}/webhook")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nStopping Instagram gateway...")
        finally:
            server.server_close()
            self._server = None

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None


def start_from_env() -> None:
    """Start the Instagram webhook gateway from ~/.zeus/.env."""
    required = {
        "ZEUS_INSTAGRAM_ACCESS_TOKEN": os.getenv("ZEUS_INSTAGRAM_ACCESS_TOKEN"),
        "ZEUS_INSTAGRAM_ACCOUNT_ID": os.getenv("ZEUS_INSTAGRAM_ACCOUNT_ID"),
        "ZEUS_INSTAGRAM_APP_SECRET": os.getenv("ZEUS_INSTAGRAM_APP_SECRET"),
        "ZEUS_INSTAGRAM_VERIFY_TOKEN": os.getenv("ZEUS_INSTAGRAM_VERIFY_TOKEN"),
    }
    missing = [key for key, value in required.items() if not value]
    if missing:
        raise RuntimeError("Instagram gateway not configured. Run `zeus setup` in the terminal.")
    gateway = InstagramGateway(
        access_token=required["ZEUS_INSTAGRAM_ACCESS_TOKEN"] or "",
        account_id=required["ZEUS_INSTAGRAM_ACCOUNT_ID"] or "",
        app_secret=required["ZEUS_INSTAGRAM_APP_SECRET"] or "",
        verify_token=required["ZEUS_INSTAGRAM_VERIFY_TOKEN"] or "",
        host=os.getenv("ZEUS_INSTAGRAM_HOST", "127.0.0.1"),
        port=int(os.getenv("ZEUS_INSTAGRAM_PORT", "8765")),
        api_version=os.getenv("ZEUS_INSTAGRAM_API_VERSION", "v26.0"),
    )
    gateway.run()
