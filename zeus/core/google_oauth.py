"""Google OAuth 2.0 device flow for Gemini browser authentication.

This module lets Zeus authenticate with Google using a browser-based OAuth
flow instead of an AI Studio API key. Tokens are stored in ~/.zeus and reused
until they expire, then refreshed automatically.
"""

import json
import os
import time
import webbrowser
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import requests

DEFAULT_CLIENT_ID = ""
DEFAULT_CLIENT_SECRET = ""

# To use Google OAuth authentication, create OAuth 2.0 credentials in the
# Google Cloud Console (https://console.cloud.google.com/apis/credentials),
# enable the Generative Language API, and set:
#   GOOGLE_OAUTH_CLIENT_ID=...apps.googleusercontent.com
#   GOOGLE_OAUTH_CLIENT_SECRET=...
# in your ~/.zeus/.env or project .env file.

# Scopes that cover Gemini Generative Language API calls.
GEMINI_SCOPES = [
    "https://www.googleapis.com/auth/generative-language.retriever",
    "https://www.googleapis.com/auth/cloud-platform",
]


def _credential_path() -> Path:
    zeus_home = Path(os.getenv("ZEUS_HOME", os.path.expanduser("~/.zeus")))
    return zeus_home / "google_device_credentials.json"


def _load_stored_credentials() -> Optional[Dict[str, Any]]:
    path = _credential_path()
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _save_credentials(data: Dict[str, Any]) -> None:
    path = _credential_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    path.chmod(0o600)


def _get_client_credentials() -> Tuple[str, str]:
    client_id = os.getenv("GOOGLE_OAUTH_CLIENT_ID") or DEFAULT_CLIENT_ID
    client_secret = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET") or DEFAULT_CLIENT_SECRET
    if not client_id or not client_secret:
        raise RuntimeError(
            "GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET must be set. "
            "Create OAuth 2.0 credentials in Google Cloud Console and add them to .env."
        )
    return client_id, client_secret


def _poll_for_token(device_code: str, client_id: str, client_secret: str) -> Dict[str, Any]:
    """Poll Google's token endpoint until the user authorizes the device."""
    interval = 5
    max_attempts = 120
    url = "https://oauth2.googleapis.com/token"
    for attempt in range(max_attempts):
        response = requests.post(
            url,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "device_code": device_code,
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            },
            timeout=30,
        )
        data = response.json()
        if response.status_code == 200:
            return data
        error = data.get("error")
        if error == "authorization_pending":
            time.sleep(interval)
            continue
        if error == "slow_down":
            interval += 2
            time.sleep(interval)
            continue
        raise RuntimeError(f"Google OAuth error: {error} - {data.get('error_description', '')}")
    raise RuntimeError("Google OAuth timeout: user did not authorize the device in time.")


def start_device_flow() -> Dict[str, Any]:
    """Start the OAuth device flow and return tokens.

    Opens the verification URL in the default browser and blocks until the user
    completes the authorization.
    """
    client_id, client_secret = _get_client_credentials()
    response = requests.post(
        "https://oauth2.googleapis.com/device/code",
        data={
            "client_id": client_id,
            "scope": " ".join(GEMINI_SCOPES),
        },
        timeout=30,
    )
    response.raise_for_status()
    device_data = response.json()

    verification_url = device_data.get("verification_url", device_data.get("verification_uri"))
    user_code = device_data["user_code"]
    device_code = device_data["device_code"]
    expires_in = device_data.get("expires_in", 1800)

    print("\n🔐 Autenticação Google necessária.")
    print(f"   Abra no navegador: {verification_url}")
    print(f"   Cole o código:     {user_code}")
    print(f"   Expira em {expires_in // 60} minutos.\n")

    try:
        webbrowser.open(verification_url)
    except Exception:
        pass

    token_data = _poll_for_token(device_code, client_id, client_secret)
    credentials = {
        "access_token": token_data["access_token"],
        "refresh_token": token_data.get("refresh_token"),
        "token_type": token_data.get("token_type", "Bearer"),
        "expires_at": int(time.time()) + token_data.get("expires_in", 3600),
        "scope": token_data.get("scope", " ".join(GEMINI_SCOPES)),
    }
    _save_credentials(credentials)
    return credentials


def refresh_access_token(refresh_token: str) -> str:
    """Refresh the access token and update stored credentials."""
    client_id, client_secret = _get_client_credentials()
    response = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    new_access_token = data["access_token"]
    expires_at = int(time.time()) + data.get("expires_in", 3600)

    credentials = _load_stored_credentials() or {}
    credentials["access_token"] = new_access_token
    credentials["expires_at"] = expires_at
    credentials["token_type"] = data.get("token_type", credentials.get("token_type", "Bearer"))
    _save_credentials(credentials)
    return new_access_token


def get_access_token(force_new: bool = False) -> str:
    """Return a valid access token, starting a browser flow if needed."""
    if force_new:
        return start_device_flow()["access_token"]

    credentials = _load_stored_credentials()
    if credentials:
        access_token = credentials["access_token"]
        refresh_token = credentials.get("refresh_token")
        if credentials.get("expires_at", 0) <= time.time() + 60:
            if refresh_token:
                return refresh_access_token(refresh_token)
        else:
            return access_token

    return start_device_flow()["access_token"]


def has_valid_credentials() -> bool:
    """Return True if there are stored non-expired credentials."""
    credentials = _load_stored_credentials()
    if not credentials:
        return False
    return credentials.get("expires_at", 0) > time.time() + 60


def revoke_credentials() -> None:
    """Delete stored Google OAuth credentials."""
    path = _credential_path()
    if path.exists():
        path.unlink()
