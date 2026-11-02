"""Base classes and resilience utilities for model providers."""

import os
import time
from http.client import RemoteDisconnected
from typing import Any, Callable, Dict, List, Optional

import requests


class TransientServerError(Exception):
    """Raised when an upstream provider returns a retryable 5xx response or 429 rate limit."""

    def __init__(self, status_code: int, body: str, retry_after: Optional[float] = None):
        self.status_code = status_code
        self.body = body
        self.retry_after = retry_after
        super().__init__(f"HTTP {status_code} from provider: {body[:300]}")


DEFAULT_RETRY_EXCEPTIONS = (
    requests.exceptions.ConnectionError,
    requests.exceptions.Timeout,
    ConnectionError,
    RemoteDisconnected,
    TransientServerError,
)


def with_retries(
    fn: Callable[[], Any],
    retries: int = 3,
    backoff: float = 1.0,
    exceptions: tuple = DEFAULT_RETRY_EXCEPTIONS,
) -> Any:
    """Retry a callable with exponential backoff on transient network and rate-limit errors."""
    last_exc: Optional[Exception] = None
    for attempt in range(retries):
        try:
            return fn()
        except exceptions as exc:
            last_exc = exc
            if attempt < retries - 1:
                sleep_time = backoff * (2**attempt)
                if isinstance(exc, TransientServerError) and exc.retry_after is not None:
                    try:
                        sleep_time = max(sleep_time, min(float(exc.retry_after), 15.0))
                    except (ValueError, TypeError):
                        pass
                time.sleep(sleep_time)
    raise last_exc  # type: ignore[misc]


def check_response_status(response: requests.Response, provider_name: str = "Provider") -> None:
    """Validate HTTP response status, raising retryable TransientServerError on 429 and 5xx."""
    status_code = getattr(response, "status_code", 200)
    if isinstance(status_code, int):
        if status_code == 429:
            retry_after_hdr = getattr(response, "headers", {}).get("Retry-After") if hasattr(response, "headers") else None
            retry_after_secs = None
            if retry_after_hdr:
                try:
                    retry_after_secs = float(retry_after_hdr)
                except (ValueError, TypeError):
                    pass
            raise TransientServerError(429, getattr(response, "text", ""), retry_after=retry_after_secs)
        if status_code >= 500:
            raise TransientServerError(status_code, getattr(response, "text", ""))
        if status_code == 400:
            try:
                error_body = response.json()
            except (ValueError, requests.exceptions.JSONDecodeError):
                error_body = {}
            error = error_body.get("error", {}) if isinstance(error_body, dict) else {}
            if isinstance(error, dict):
                detail = error.get("message") or error.get("detail") or error.get("type")
            elif isinstance(error, str):
                detail = error
            else:
                detail = None
            raise RuntimeError(f"{provider_name} bad request (400): {str(detail or 'invalid request')[:500]}")
    if hasattr(response, "raise_for_status"):
        response.raise_for_status()
