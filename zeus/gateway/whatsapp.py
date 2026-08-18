"""WhatsApp gateway for Zeus using the Baileys local HTTP bridge.

This gateway polls a local Baileys HTTP server for incoming WhatsApp messages,
dispatches them to the Zeus agent, and sends replies back.
"""

import os
import time
from typing import Any, Dict, List, Optional, Set

import requests

from zeus.core.agent import run_agent
from zeus.gateway.confirmations import ConfirmationManager
from zeus.memory.session_log import get_logger
from zeus.tools.file import set_file_permission_callback


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
        self._confirmations = ConfirmationManager()
        self._pending_inputs: Dict[str, str] = {}
        self._setup_permissions()

    def _setup_permissions(self) -> None:
        """Configure file permission callback for this gateway."""
        def callback(_message: str) -> bool:
            return False
        set_file_permission_callback(callback)

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

        user_id = from_jid

        # Handle pending file permission confirmations.
        if self._confirmations.answer("whatsapp", user_id, text):
            return

        # Handle pending input resumption.
        if user_id in self._pending_inputs:
            original_input = self._pending_inputs.pop(user_id)
            text = f"{original_input}\n\nConfirmação do usuário: {text}"

        print(f"WhatsApp message from {from_jid}: {text[:80]}")
        session_id = f"whatsapp-{from_jid.replace('@', '-')}"
        logger = get_logger(session_id)
        logger.log_turn(
            "user",
            text,
            metadata={"from": from_jid, "timestamp": timestamp, "user_id": user_id},
        )

        try:
            response = run_agent(
                text,
                session_id=logger.session_id,
                user_id=user_id,
                platform="whatsapp",
            )

            if isinstance(response, dict) and response.get("permission_required"):
                perm = response["permission_required"]
                action = perm.get("action", "write")
                path = perm.get("path", "")
                self._confirmations.request(
                    "whatsapp",
                    user_id,
                    action,
                    path,
                    on_response=lambda choice, original=text, target=from_jid, sid=logger.session_id, a=action, p=path: (
                        self._resume_after_confirmation(original, choice, target, sid, user_id, action=a, path=p)
                    ),
                )
                self.send_message(from_jid, self._confirmations.format_question(action, path))
                return

            logger.log_turn(
                "assistant",
                response,
                metadata={"from": from_jid, "user_id": user_id},
            )
            self.send_message(from_jid, response)
        except Exception as e:
            logger.log_turn("error", str(e), metadata={"from": from_jid})
            print(f"Error handling message: {e}")
            self.send_message(from_jid, f"Erro: {e}")

    def _resume_after_confirmation(
        self,
        original_input: str,
        choice: str,
        target: str,
        logger_session_id: str,
        user_id: str,
        action: str = "write",
        path: str = "",
    ) -> None:
        if choice == "deny":
            self.send_message(target, "Ação negada pelo usuário.")
            return

        from pathlib import Path
        from zeus.tools.file import get_file_permission_manager

        pm = get_file_permission_manager()
        pm.grant_permission(action, Path(path) if path else None, scope=choice)

        if choice == "once":
            instruction = f"{original_input}\n\n[O usuário permitiu a ação de arquivo desta vez.]"
        elif choice == "always":
            instruction = f"{original_input}\n\n[O usuário permitiu a ação de arquivo para esta sessão.]"
        elif choice == "persist":
            instruction = f"{original_input}\n\n[O usuário permitiu a ação de arquivo permanentemente.]"
        else:
            instruction = original_input

        self._pending_inputs[user_id] = instruction

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
