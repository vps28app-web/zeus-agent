"""Rate limiting for security-sensitive operations."""

import threading
import time
from collections import deque
from typing import Dict, Optional


class RateLimiter:
    """Sliding-window rate limiter per action, optionally scoped by user/session."""

    def __init__(
        self,
        max_per_minute: int = 60,
        max_per_hour: int = 500,
        max_per_minute_per_user: int = 20,
        max_per_hour_per_user: int = 200,
    ):
        self.max_per_minute = max_per_minute
        self.max_per_hour = max_per_hour
        self.max_per_minute_per_user = max_per_minute_per_user
        self.max_per_hour_per_user = max_per_hour_per_user
        self._windows: Dict[str, deque] = {}
        self._user_windows: Dict[str, deque] = {}
        self._lock = threading.Lock()

    def _count_window(self, window: deque, since: float) -> int:
        return sum(1 for ts in window if ts >= since)

    def _prune(self, window: deque, now: float) -> None:
        while window and window[0] < now - 3600:
            window.popleft()

    def is_allowed(
        self,
        action: str,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> bool:
        """Return True if the action is within global and per-user quotas."""
        now = time.time()
        global_key = action
        user_key = f"{action}:{user_id or 'anonymous'}"
        session_key = f"{action}:{user_id or 'anonymous'}:{session_id or 'global'}"

        with self._lock:
            # Global window
            global_window = self._windows.setdefault(global_key, deque())
            self._prune(global_window, now)
            if self._count_window(global_window, now - 60) >= self.max_per_minute:
                return False
            if len(global_window) >= self.max_per_hour:
                return False

            # Per-user window (across sessions)
            user_window = self._user_windows.setdefault(user_key, deque())
            self._prune(user_window, now)
            if self._count_window(user_window, now - 60) >= self.max_per_minute_per_user:
                return False
            if len(user_window) >= self.max_per_hour_per_user:
                return False

            global_window.append(now)
            user_window.append(now)
            # Also track per-session via the same deque by appending with session id would require new structure.
            # For simplicity, session-level is included in user counts; global is separate.
            return True

    def reset(
        self,
        action: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> None:
        with self._lock:
            if action is None and user_id is None:
                self._windows.clear()
                self._user_windows.clear()
                return
            keys_to_remove = []
            for key in list(self._windows.keys()):
                if action is None or key == action or key.startswith(f"{action}:"):
                    if user_id is None or user_id in key:
                        keys_to_remove.append(key)
            for key in keys_to_remove:
                self._windows.pop(key, None)
                self._user_windows.pop(key, None)


# Singleton process-wide rate limiter.
_EXECUTION_LIMITER: Optional[RateLimiter] = None
_EXECUTION_LIMITER_LOCK = threading.Lock()


def get_execution_limiter() -> RateLimiter:
    global _EXECUTION_LIMITER
    if _EXECUTION_LIMITER is None:
        with _EXECUTION_LIMITER_LOCK:
            if _EXECUTION_LIMITER is None:
                _EXECUTION_LIMITER = RateLimiter()
    return _EXECUTION_LIMITER
