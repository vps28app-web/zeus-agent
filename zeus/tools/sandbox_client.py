"""Client for the Zeus Go sandbox server."""

import os
from typing import Any, Dict, Optional

import requests

# Environment variables allowed to be forwarded to sandbox/terminal subprocesses.
# Sensitive credentials (API keys, tokens, passwords) are excluded by default.
ALLOWED_ENV_VARS = {
    "PATH",
    "HOME",
    "USER",
    "SHELL",
    "LANG",
    "LC_ALL",
    "TZ",
    "TERM",
    "PWD",
    "OLDPWD",
    "PYTHONPATH",
    "PYTHONDONTWRITEBYTECODE",
    "PYTHONUNBUFFERED",
    "ZEUS_HOME",
    "ZEUS_PROJECT_DIR",
    "ZEUS_SANDBOX_URL",
}


def safe_environment(extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """Return a sanitized environment dict for subprocess execution."""
    env = {k: v for k, v in os.environ.items() if k in ALLOWED_ENV_VARS}
    if extra:
        # Only allow extra keys that do not look like secrets.
        for key, value in extra.items():
            if any(secret in key.lower() for secret in ("key", "token", "secret", "password", "api")):
                continue
            env[key] = value
    return env


def current_user_session() -> tuple[Optional[str], Optional[str]]:
    """Return (user_id, session_id) from environment if available."""
    return (
        os.getenv("ZEUS_USER_ID") or None,
        os.getenv("ZEUS_SESSION_ID") or None,
    )


DEFAULT_URL = "http://127.0.0.1:9876"


def _sandbox_headers() -> Dict[str, str]:
    """Return Authorization header if ZEUS_SANDBOX_AUTH_TOKEN is configured."""
    token = os.getenv("ZEUS_SANDBOX_AUTH_TOKEN")
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {}


def is_sandbox_available(url: Optional[str] = None) -> bool:
    """Return True if the sandbox server responds to health check."""
    base_url = (url or os.getenv("ZEUS_SANDBOX_URL", DEFAULT_URL)).rstrip("/")
    try:
        response = requests.get(f"{base_url}/health", timeout=2, headers=_sandbox_headers())
        return response.status_code == 200
    except requests.RequestException:
        return False


def run_sandboxed_command(
    command: str,
    timeout: int = 30,
    env: Optional[Dict[str, str]] = None,
    work_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """Send a command to the sandbox server; reject unsupported custom work dirs."""
    if work_dir:
        return {
            "error": "work_dir is not supported; sandbox workspaces are always created in a private temporary directory"
        }
    base_url = os.getenv("ZEUS_SANDBOX_URL", DEFAULT_URL).rstrip("/")
    if not is_sandbox_available(base_url):
        return {
            "error": (
                f"Sandbox server not available at {base_url}. "
                "Start it with: ./sandbox/cmd/sandbox/sandbox"
            ),
        }
    payload = {
        "command": command,
        "timeout_sec": timeout,
    }
    if env:
        payload["env"] = env
    if work_dir:
        payload["work_dir"] = work_dir

    try:
        response = requests.post(  # nosec B113
            f"{base_url}/run",
            json=payload,
            timeout=timeout + 5,
            headers=_sandbox_headers(),
        )
        if response.status_code >= 400:
            try:
                error_payload = response.json()
            except ValueError:
                error_payload = None
            if isinstance(error_payload, dict) and error_payload.get("error"):
                return error_payload
            response.raise_for_status()
        return response.json()
    except requests.ConnectionError:
        return {
            "error": f"Sandbox server not available at {base_url}. Start it with: ./sandbox/cmd/sandbox/sandbox",
        }
    except requests.RequestException as e:
        return {"error": str(e)}


def health_check(url: Optional[str] = None) -> Dict[str, Any]:
    base_url = (url or os.getenv("ZEUS_SANDBOX_URL", DEFAULT_URL)).rstrip("/")
    try:
        response = requests.get(f"{base_url}/health", timeout=5, headers=_sandbox_headers())
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        return {"error": str(e)}
