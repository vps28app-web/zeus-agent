"""WhatsApp gateway for Zeus using the Baileys local HTTP bridge.

This gateway polls a local Baileys HTTP server for incoming WhatsApp messages,
dispatches them to the Zeus agent, and sends replies back.
"""

import os
import time
from typing import Any, Dict, List, Optional, Set

import requests

from zeus.core.agent import run_agent
from zeus.memory.session_log import get_logger


class WhatsAppGateway:
    """Polls the Baileys bridge and dispatches messages to the Zeus agent."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:9877",
        allowed_numbers: Optional[List[str]] = None,
        poll_interval: float = 2.0,
        timeout: int = 30,
    ):
        self.base_url = base_url.rstrip("/")
        self.allowed_numbers: Set[str] = set(allowed_numbers or [])
        self.poll_interval = poll_interval
        self.timeout = timeout
        self.running = False

    def _get(self, path: str) -> Dict[str, Any]:
        response = requests.get(f"{self.base_url}{path}", timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def _post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        response = requests.post(
            f"{self.base_url}{path}",
            json=payload,
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def health(self) -> Dict[str, Any]:
        return self._get("/health")

    def connection(self) -> str:
        try:
            data = self._get("/connection")
            return str(data.get("connection", "unknown"))
        except Exception:
            return "unreachable"

    def send_message(self, to: str, text: str) -> None:
        """Send a text message to a WhatsApp number (jid format)."""
        chunks = self._chunk_text(text)
        for chunk in chunks:
            self._post("/send", {"to": to, "text": chunk})

    @staticmethod
    def _chunk_text(text: str, max_length: int = 4000) -> List[str]:
        if len(text) <= max_length:
            return [text]
        chunks = []
        while text:
            chunks.append(text[:max_length])
            text = text[max_length:]
        return chunks

    def get_messages(self) -> List[Dict[str, Any]]:
        return self._get("/messages").get("messages", [])

    def is_allowed(self, number: str) -> bool:
        if not self.allowed_numbers:
            return False
        return number in self.allowed_numbers

    def handle_message(self, msg: Dict[str, Any]) -> None:
        from_jid = msg.get("from", "")
        text = msg.get("text", "").strip()
        timestamp = msg.get("timestamp")

        if not text or not from_jid:
            return

        if not self.is_allowed(from_jid):
            print(f"Ignoring message from unauthorized number: {from_jid}")
            return

        connection = self.connection()
        if connection != "connected":
            print(f"WhatsApp not connected ({connection}); skipping message from {from_jid}")
            return

        print(f"WhatsApp message from {from_jid}: {text[:80]}")
        session_id = f"whatsapp-{from_jid.replace('@', '-')}"
        logger = get_logger(session_id)
        logger.log_turn("user", text, metadata={"from": from_jid, "timestamp": timestamp})

        try:
            response = run_agent(text, session_id=logger.session_id)
            logger.log_turn("assistant", response, metadata={"from": from_jid})
            self.send_message(from_jid, response)
        except Exception as e:
            logger.log_turn("error", str(e), metadata={"from": from_jid})
            print(f"Error handling message: {e}")
            self.send_message(from_jid, f"Erro: {e}")

    def run(self) -> None:
        self.running = True
        print("WhatsApp gateway started. Press Ctrl+C to stop.")
        while self.running:
            try:
                messages = self.get_messages()
                for msg in messages:
                    self.handle_message(msg)
                if len(messages) == 0:
                    time.sleep(self.poll_interval)
            except KeyboardInterrupt:
                print("\nStopping WhatsApp gateway...")
                self.running = False
            except Exception as e:
                print(f"Polling error: {e}")
                time.sleep(self.poll_interval)

    def stop(self) -> None:
        self.running = False


def start_from_env() -> None:
    """Start WhatsApp gateway using environment variables."""
    base_url = os.getenv("ZEUS_WHATSAPP_URL", "http://127.0.0.1:9877")
    raw_numbers = os.getenv("ZEUS_WHATSAPP_ALLOWED_NUMBERS", "")
    allowed_numbers = []
    if raw_numbers:
        allowed_numbers = [n.strip() for n in raw_numbers.split(",") if n.strip()]

    gateway = WhatsAppGateway(
        base_url=base_url,
        allowed_numbers=allowed_numbers,
        poll_interval=float(os.getenv("ZEUS_WHATSAPP_POLL_INTERVAL", "2.0")),
    )
    gateway.run()
