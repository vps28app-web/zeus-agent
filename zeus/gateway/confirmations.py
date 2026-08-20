"""Pending confirmation manager for gateway file permissions."""

import threading
import time
from typing import Any, Callable, Dict, Optional


class ConfirmationManager:
    """Track pending file permission confirmations per user/chat."""

    def __init__(self, default_timeout: float = 300.0):
        self._pending: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        self.default_timeout = default_timeout

    def _key(self, platform: str, user_id: str) -> str:
        return f"{platform}:{user_id}"

    def request(
        self,
        platform: str,
        user_id: str,
        action: str,
        path: str,
        on_response: Callable[[str], None],
    ) -> None:
        """Store a pending confirmation and notify caller when answered."""
        with self._lock:
            self._pending[self._key(platform, user_id)] = {
                "action": action,
                "path": path,
                "on_response": on_response,
                "expires_at": time.time() + self.default_timeout,
            }

    def answer(self, platform: str, user_id: str, text: str) -> bool:
        """Process a user response to a pending confirmation."""
        key = self._key(platform, user_id)
        with self._lock:
            pending = self._pending.get(key)
            if not pending:
                return False
            if time.time() > pending["expires_at"]:
                del self._pending[key]
                return False

            choice = text.strip().lower()
            if choice in ("y", "yes", "s", "sim"):
                response = "once"
            elif choice in ("a", "always"):
                response = "always"
            elif choice in ("p", "persist"):
                response = "persist"
            else:
                response = "deny"

            callback = pending["on_response"]
            del self._pending[key]

        callback(response)
        return True

    def has_pending(self, platform: str, user_id: str) -> bool:
        key = self._key(platform, user_id)
        with self._lock:
            pending = self._pending.get(key)
            if not pending:
                return False
            if time.time() > pending["expires_at"]:
                del self._pending[key]
                return False
            return True

    def format_question(self, action: str, path: str) -> str:
        action_title = "Write / Escrita ✍️" if action == "write" else "Delete / Exclusão 🗑️" if action == "delete" else action.capitalize()
        return (
            f"🔒 File permission required / Permissão de arquivo necessária:\n"
            f"  • Operation / Operação: {action_title}\n"
            f"  • File / Arquivo: {path}\n\n"
            f"Reply / Responda:\n"
            f"  • (y) yes / sim (once / uma vez)\n"
            f"  • (a) always / sempre (this session / nesta sessão)\n"
            f"  • (p) persist / persistir (permanent / permanente)\n"
            f"  • (n) no / negar"
        )
