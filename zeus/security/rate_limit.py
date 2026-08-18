"""Rate limiting for security-sensitive operations."""

import threading
import time
from collections import deque
from typing import Dict, Optional


class RateLimiter:
    """Simple sliding-window rate limiter per action."""

    def __init__(
        self,
        max_per_minute: int = 60,
        max_per_hour: int = 500,
    ):
        self.max_per_minute = max_per_minute
        self.max_per_hour = max_per_hour
        self._windows: Dict[str, deque] = {}
        self._lock = threading.Lock()

    def is_allowed(self, action: str) -> bool:
        now = time.time()
        with self._lock:
            window = self._windows.setdefault(action, deque())
            # Drop entries older than 1 hour.
            while window and window[0] < now - 3600:
                window.popleft()

            # Count entries within the last minute.
            minute_ago = now - 60
            last_minute = sum(1 for ts in window if ts >= minute_ago)
            if last_minute >= self.max_per_minute:
                return False
            if len(window) >= self.max_per_hour:
                return False

            window.append(now)
            return True

    def reset(self, action: Optional[str] = None) -> None:
        with self._lock:
            if action is None:
                self._windows.clear()
            else:
                self._windows.pop(action, None)


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
