"""Telegram bot gateway for Zeus.

Uses raw HTTP polling to avoid heavy dependencies.
Only responds to messages from configured allowed chat IDs.
"""

import os
import threading
import time
from typing import Any, Dict, List, Optional, Set

import requests

from zeus.core.agent import run_agent
from zeus.gateway.confirmations import ConfirmationManager
from zeus.memory.session_log import get_logger
from zeus.tools.file import set_file_permission_callback

DEFAULT_AGENT_TIMEOUT = float(os.getenv("ZEUS_GATEWAY_AGENT_TIMEOUT", "120"))


def _run_agent_with_timeout(
    text: str,
    session_id: Optional[str],
    user_id: Optional[str] = None,
    platform: Optional[str] = None,
    timeout: float = DEFAULT_AGENT_TIMEOUT,
):
    """Run the agent in a background thread and return the result or raise TimeoutError."""
    result: Dict[str, Any] = {"value": None, "error": None}

    def target():
        try:
            result["value"] = run_agent(
                text,
                session_id=session_id,
                user_id=user_id,
                platform=platform,
            )
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
        self._confirmations = ConfirmationManager()
        self._pending_inputs: Dict[str, str] = {}
        self._setup_permissions()

    def _setup_permissions(self) -> None:
        """Configure permission callbacks for this gateway."""
        def callback(_message: str) -> bool:
            # Synchronous denial: the gateway will ask via a follow-up message.
            return False
        set_file_permission_callback(callback)
        # Wire gateway confirmation manager into the global PermissionManager so
        # terminal-mode tool confirmations can also prompt the user.
        from zeus.security.permissions import PermissionManager, set_global_permission_manager
        set_global_permission_manager(PermissionManager(confirm_callback=callback))

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
        response = requests.post(  # nosec B113
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

        user_id = str(chat_id)

        # Handle pending file permission confirmations.
        if self._confirmations.answer("telegram", user_id, text):
            return

        from zeus.gateway.commands import handle_zeus_command
        admin_response = handle_zeus_command(text)
        if admin_response is not None:
            self.send_message(chat_id, admin_response, reply_to_message_id=message_id)
            return

        # Handle pending input resumption.
        if user_id in self._pending_inputs:
            original_input = self._pending_inputs.pop(user_id)
            text = f"{original_input}\n\nConfirmação do usuário: {text}"

        def worker():
            logger = get_logger(f"telegram-{chat_id}-{message_id}")
            logger.log_turn(
                "user",
                text,
                metadata={"chat_id": chat_id, "username": username, "user_id": user_id},
            )

            typing_stop = threading.Event()
            typing_thread = threading.Thread(
                target=self._typing_indicator,
                args=(chat_id, typing_stop),
                daemon=True,
            )
            typing_thread.start()

            try:
                response = _run_agent_with_timeout(
                    text,
                    session_id=logger.session_id,
                    user_id=user_id,
                    platform="telegram",
                )

                # Check if a file or terminal permission confirmation was triggered.
                if isinstance(response, dict) and response.get("permission_required"):
                    perm = response["permission_required"]
                    action = perm.get("action", "write")
                    path = perm.get("path", "")
                    self._confirmations.request(
                        "telegram",
                        user_id,
                        action,
                        path,
                        on_response=lambda choice, original=text, cid=chat_id, mid=message_id, sid=logger.session_id, a=action, p=path: (
                            self._resume_after_confirmation(original, choice, cid, mid, sid, user_id, action=a, path=p)
                        ),
                    )
                    self.send_message(chat_id, self._confirmations.format_question(action, path), reply_to_message_id=message_id)
                    return

                # Terminal-mode confirmations are triggered when the tool returns
                # an explicit denial and the command is awaiting user approval.
                terminal_err = response.get("error", "") if isinstance(response, dict) else ""
                if isinstance(terminal_err, str) and terminal_err.startswith("Execution confirmation / Confirmação de execução"):
                    command = self._extract_command_from_confirmation(terminal_err)
                    self._confirmations.request(
                        "telegram",
                        user_id,
                        "terminal",
                        command,
                        on_response=lambda choice, original=text, cid=chat_id, mid=message_id, sid=logger.session_id, cmd=command: (
                            self._resume_after_terminal_confirmation(original, choice, cid, mid, sid, user_id, cmd)
                        ),
                    )
                    question = self._confirmations.format_question("terminal", command)
                    self.send_message(chat_id, question, reply_to_message_id=message_id)
                    return

                logger.log_turn(
                    "assistant",
                    response,
                    metadata={"chat_id": chat_id, "user_id": user_id},
                )
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

    def _extract_command_from_confirmation(self, message: str) -> str:
        """Extract the command from a terminal confirmation summary."""
        for line in message.splitlines():
            if line.strip().startswith("• Command / Comando:"):
                return line.split(":", 1)[1].strip()
        return ""

    def _resume_after_terminal_confirmation(
        self,
        original_input: str,
        choice: str,
        chat_id: int,
        message_id: int,
        logger_session_id: str,
        user_id: str,
        command: str,
    ) -> None:
        """Resume agent execution after user confirms/denies a terminal command."""
        if choice == "deny":
            self.send_message(chat_id, "Ação negada pelo usuário / Action denied by user.", reply_to_message_id=message_id)
            return

        from zeus.security.permissions import get_global_permission_manager

        pm = get_global_permission_manager()
        if choice in ("always", "persist"):
            pm.grant_permission("tool:run_terminal", None, scope=choice)
        if choice == "once":
            pm._once_confirmed_actions.add(f"tool:run_terminal:{command}")

        instruction = (
            f"{original_input}\n\n"
            f"[O usuário permitiu a execução do comando '{command}' "
            f"({'desta vez' if choice == 'once' else 'nesta sessão' if choice == 'always' else 'permanentemente'}). "
            f"Execute o comando e retorne o resultado.]"
        )

        def worker():
            logger = get_logger(logger_session_id)
            try:
                response = _run_agent_with_timeout(
                    instruction,
                    session_id=logger.session_id,
                    user_id=user_id,
                    platform="telegram",
                )
                logger.log_turn("assistant", response, metadata={"chat_id": chat_id, "user_id": user_id})
                self.send_message(chat_id, response, reply_to_message_id=message_id)
            except Exception as e:
                logger.log_turn("error", str(e), metadata={"chat_id": chat_id})
                self.send_message(chat_id, f"Erro ao executar após autorização: {e}", reply_to_message_id=message_id)

        t = threading.Thread(target=worker, daemon=True)
        t.start()
        self._worker_threads.append(t)
        self._worker_threads = [t for t in self._worker_threads if t.is_alive()]

    def _resume_after_confirmation(
        self,
        original_input: str,
        choice: str,
        chat_id: int,
        message_id: int,
        logger_session_id: str,
        user_id: str,
        action: str = "write",
        path: str = "",
    ) -> None:
        """Resume agent execution immediately after user confirms/denies a file action."""
        if choice == "deny":
            self.send_message(chat_id, "Ação negada pelo usuário / Action denied by user.", reply_to_message_id=message_id)
            return

        from pathlib import Path

        from zeus.tools.file import get_file_permission_manager

        pm = get_file_permission_manager()
        pm.grant_permission(action, Path(path) if path else None, scope=choice)

        if choice == "once":
            instruction = f"{original_input}\n\n[O usuário permitiu a ação de arquivo ({action}) desta vez. Execute a ação e retorne o resultado.]"
        elif choice == "always":
            instruction = f"{original_input}\n\n[O usuário permitiu a ação de arquivo ({action}) para esta sessão. Execute a ação e retorne o resultado.]"
        elif choice == "persist":
            instruction = f"{original_input}\n\n[O usuário permitiu a ação de arquivo ({action}) permanentemente. Execute a ação e retorne o resultado.]"
        else:
            instruction = original_input

        def worker():
            logger = get_logger(logger_session_id)
            try:
                response = _run_agent_with_timeout(
                    instruction,
                    session_id=logger.session_id,
                    user_id=user_id,
                    platform="telegram",
                )
                logger.log_turn("assistant", response, metadata={"chat_id": chat_id, "user_id": user_id})
                self.send_message(chat_id, response, reply_to_message_id=message_id)
            except Exception as e:
                logger.log_turn("error", str(e), metadata={"chat_id": chat_id})
                self.send_message(chat_id, f"Erro ao executar após autorização: {e}", reply_to_message_id=message_id)

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
