"""Client for the Zeus Go sandbox server."""

import os
from typing import Any, Dict, Optional

import requests


DEFAULT_URL = "http://127.0.0.1:9876"


def run_sandboxed_command(
    command: str,
    timeout: int = 30,
    env: Optional[Dict[str, str]] = None,
    work_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """Send a command to the sandbox server and return the result."""
    base_url = os.getenv("ZEUS_SANDBOX_URL", DEFAULT_URL).rstrip("/")
    payload = {
        "command": command,
        "timeout_sec": timeout,
    }
    if env:
        payload["env"] = env
    if work_dir:
        payload["work_dir"] = work_dir

    try:
        response = requests.post(
            f"{base_url}/run",
            json=payload,
            timeout=timeout + 5,
        )
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
        response = requests.get(f"{base_url}/health", timeout=5)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        return {"error": str(e)}
