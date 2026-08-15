"""Telegram bot gateway for Zeus.

Uses raw HTTP polling to avoid heavy dependencies.
Only responds to messages from configured allowed chat IDs.
"""

import json
import os
import threading
import time
from typing import Any, Dict, List, Optional, Set

import requests

from zeus.core.agent import run_agent
from zeus.memory.session_log import get_logger


DEFAULT_AGENT_TIMEOUT = float(os.getenv("ZEUS_GATEWAY_AGENT_TIMEOUT", "120"))


def _run_agent_with_timeout(text: str, session_id: Optional[str], timeout: float = DEFAULT_AGENT_TIMEOUT):
    """Run the agent in a background thread and return the result or raise TimeoutError."""
    result: Dict[str, Any] = {"value": None, "error": None}

    def target():
        try:
            result["value"] = run_agent(text, session_id=session_id)
        except Exception as e:
            result["error"] = e

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    thread.join(timeout)

    if thread.is_alive():
        raise TimeoutError(f"Agent took longer than {timeout}s")
    if result["error"]:
        raise result["error"]
    return result["value"]


class TelegramGateway:
    """Polls Telegram for messages and dispatches them to the Zeus agent."""

    def __init__(
        self,
        token: str,
        allowed_chat_ids: Optional[List[int]] = None,
        base_url: str = "https://api.telegram.org",
        poll_interval: float = 1.0,
        timeout: int = 30,
        poll_timeout: int = 5,
    ):
        self.token = token
        self.base_url = base_url.rstrip("/")
        self.poll_interval = poll_interval
        self.timeout = timeout
        self.poll_timeout = poll_timeout
        self.allowed_chat_ids: Set[int] = set(allowed_chat_ids or [])
        self.offset: Optional[int] = None
        self.running = False
        self._worker_threads: List[threading.Thread] = []

    def api_url(self, method: str) -> str:
        return f"{self.base_url}/bot{self.token}/{method}"

    def _post(self, method: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        response = requests.post(
            self.api_url(method),
            json=payload,
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def send_chat_action(self, chat_id: int, action: str = "typing") -> None:
        """Send a chat action (typing, uploading_photo, etc.)."""
        try:
            self._post("sendChatAction", {"chat_id": chat_id, "action": action})
        except Exception:
            # Chat action is best-effort; don't fail the whole request.
            pass

    def _typing_indicator(self, chat_id: int, stop_event: threading.Event, interval: float = 4.0):
        """Keep sending typing actions until stop_event is set."""
        while not stop_event.is_set():
            self.send_chat_action(chat_id, "typing")
            stop_event.wait(interval)

    def send_message(self, chat_id: int, text: str, reply_to_message_id: Optional[int] = None) -> None:
        """Send a text message back to a Telegram chat."""
        chunks = self._chunk_text(text)
        for chunk in chunks:
            payload = {
                "chat_id": chat_id,
                "text": _escape_html(chunk),
                "parse_mode": "HTML",
            }
            if reply_to_message_id:
                payload["reply_to_message_id"] = reply_to_message_id
            self._post("sendMessage", payload)

    @staticmethod
    def _chunk_text(text: str, max_length: int = 4000) -> List[str]:
        """Split long messages to fit Telegram limits."""
        if len(text) <= max_length:
            return [text]
        chunks = []
        while text:
            chunk = text[:max_length]
            text = text[max_length:]
            chunks.append(chunk)
        return chunks

    def get_updates(self) -> List[Dict[str, Any]]:
        """Fetch new messages from Telegram."""
        payload = {
            "offset": self.offset,
            "limit": 100,
            "timeout": int(self.poll_timeout),
        }
        response = requests.post(
            self.api_url("getUpdates"),
            json=payload,
            timeout=self.poll_timeout + 10,
        )
        response.raise_for_status()
        data = response.json()
        if not data.get("ok"):
            raise RuntimeError(f"Telegram API error: {data}")
        return data.get("result", [])

    def is_allowed(self, chat_id: int) -> bool:
        if not self.allowed_chat_ids:
            return False
        return chat_id in self.allowed_chat_ids

    def handle_update(self, update: Dict[str, Any]) -> None:
        """Process a single Telegram update in a background worker thread."""
        message = update.get("message") or update.get("edited_message")
        if not message:
            return

        chat = message.get("chat", {})
        chat_id = chat.get("id")
        text = message.get("text", "").strip()
        message_id = message.get("message_id")
        username = chat.get("username") or chat.get("first_name") or str(chat_id)

        if not text or chat_id is None:
            return

        if not self.is_allowed(chat_id):
            print(f"Ignoring message from unauthorized chat: {chat_id}")
            return

        print(f"Message from {username} ({chat_id}): {text[:80]}")

        def worker():
            logger = get_logger(f"telegram-{chat_id}-{message_id}")
            logger.log_turn("user", text, metadata={"chat_id": chat_id, "username": username})

            typing_stop = threading.Event()
            typing_thread = threading.Thread(
                target=self._typing_indicator,
                args=(chat_id, typing_stop),
                daemon=True,
            )
            typing_thread.start()

            try:
                response = _run_agent_with_timeout(text, session_id=logger.session_id)
                logger.log_turn("assistant", response, metadata={"chat_id": chat_id})
                self.send_message(chat_id, response, reply_to_message_id=message_id)
            except TimeoutError as e:
                logger.log_turn("error", str(e), metadata={"chat_id": chat_id})
                print(f"Agent timeout: {e}")
                self.send_message(chat_id, "Demorou muito para responder. Tente novamente ou reformule a pergunta.", reply_to_message_id=message_id)
            except Exception as e:
                logger.log_turn("error", str(e), metadata={"chat_id": chat_id})
                print(f"Error handling message: {e}")
                self.send_message(chat_id, f"Erro: {e}", reply_to_message_id=message_id)
            finally:
                typing_stop.set()
                typing_thread.join(timeout=1)

        t = threading.Thread(target=worker, daemon=True)
        t.start()
        self._worker_threads.append(t)
        self._worker_threads = [t for t in self._worker_threads if t.is_alive()]

    def run(self) -> None:
        """Start polling loop."""
        self.running = True
        print("Telegram gateway started. Press Ctrl+C to stop.")
        while self.running:
            try:
                updates = self.get_updates()
                for update in updates:
                    self.handle_update(update)
                    update_id = update.get("update_id")
                    if update_id is not None:
                        self.offset = update_id + 1
                if len(updates) < 100:
                    time.sleep(self.poll_interval)
            except KeyboardInterrupt:
                print("\nStopping Telegram gateway...")
                self.running = False
            except Exception as e:
                print(f"Polling error: {e}")
                time.sleep(self.poll_interval)

    def stop(self) -> None:
        self.running = False
        for t in self._worker_threads:
            if t.is_alive():
                t.join(timeout=5)


def start_from_env() -> None:
    """Start Telegram gateway using environment variables."""
    token = os.getenv("ZEUS_TELEGRAM_TOKEN")
    if not token:
        raise RuntimeError("ZEUS_TELEGRAM_TOKEN not set")

    raw_ids = os.getenv("ZEUS_TELEGRAM_ALLOWED_CHAT_IDS", "")
    allowed_chat_ids = []
    if raw_ids:
        allowed_chat_ids = [int(x.strip()) for x in raw_ids.split(",") if x.strip()]

    gateway = TelegramGateway(
        token=token,
        allowed_chat_ids=allowed_chat_ids,
        poll_interval=float(os.getenv("ZEUS_TELEGRAM_POLL_INTERVAL", "1.0")),
        poll_timeout=int(os.getenv("ZEUS_TELEGRAM_POLL_TIMEOUT", "5")),
    )
    gateway.run()


def _escape_html(text: str) -> str:
    """Escape characters that have special meaning in Telegram HTML mode."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
