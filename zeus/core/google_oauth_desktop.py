"""Google OAuth 2.0 authorization code flow with localhost redirect.

This module implements the OAuth 2.0 authorization code flow with PKCE for
CLI/desktop applications. It starts a temporary HTTP server on 127.0.0.1,
opens the user's browser to Google's consent screen, and receives the
authorization code via redirect.

The obtained tokens are stored in ~/.zeus/google_oauth_credentials.json and
refreshed automatically when expired.

To use this flow, create OAuth 2.0 credentials in Google Cloud Console with
application type "Desktop app" and set:
    GOOGLE_OAUTH_CLIENT_ID=...apps.googleusercontent.com
    GOOGLE_OAUTH_CLIENT_SECRET=...
"""

import base64
import hashlib
import json
import os
import secrets
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Thread
from typing import Any, Dict, Optional, Tuple
from urllib.parse import parse_qs, urlparse

import requests

# Scopes for the Gemini Generative Language API.
GEMINI_SCOPES = [
    "https://www.googleapis.com/auth/generative-language.retriever",
    "https://www.googleapis.com/auth/cloud-platform",
]

AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"


def _credential_path() -> Path:
    zeus_home = Path(os.getenv("ZEUS_HOME", os.path.expanduser("~/.zeus")))
    return zeus_home / "google_oauth_credentials.json"


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
    client_id = os.getenv("GOOGLE_OAUTH_CLIENT_ID", "")
    client_secret = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        raise RuntimeError(
            "GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET must be set. "
            "Create OAuth 2.0 credentials (Desktop app) in Google Cloud Console."
        )
    return client_id, client_secret


def _generate_pkce_pair() -> Tuple[str, str]:
    """Return (code_verifier, code_challenge) using S256 method."""
    verifier = base64.urlsafe_b64encode(os.urandom(32)).rstrip(b"=").decode("ascii")
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest())
        .rstrip(b"=")
        .decode("ascii")
    )
    return verifier, challenge


class _RedirectHandler(BaseHTTPRequestHandler):
    """HTTP handler that captures the OAuth authorization code."""

    code: Optional[str] = None
    error: Optional[str] = None
    error_description: Optional[str] = None

    def log_message(self, format: str, *args: Any) -> None:
        # Suppress default logging to keep CLI clean.
        pass

    def _send_landing_page(self, status: int, title: str, body: str) -> None:
        html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>{title}</title>
<style>
  body {{ font-family: system-ui, sans-serif; text-align: center; padding: 3rem; }}
  .card {{ display: inline-block; padding: 2rem; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.15); }}
  h1 {{ margin-top: 0; }}
</style>
</head>
<body>
  <div class="card">
    <h1>{title}</h1>
    <p>{body}</p>
    <p>Voc&ecirc; pode fechar esta aba e voltar ao terminal.</p>
  </div>
</body>
</html>"""
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)

        if "code" in query:
            _RedirectHandler.code = query["code"][0]
            self._send_landing_page(200, "Autenticação concluída", "O Zeus recebeu o código de autorização.")
        elif "error" in query:
            _RedirectHandler.error = query["error"][0]
            _RedirectHandler.error_description = query.get("error_description", [""])[0]
            self._send_landing_page(
                400,
                "Autenticação falhou",
                f"Erro: {_RedirectHandler.error} - {_RedirectHandler.error_description}",
            )
        else:
            self.send_response(404)
            self.end_headers()


def _find_free_port() -> int:
    """Find a free localhost port."""
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def start_authorization_flow(timeout: int = 300) -> Dict[str, Any]:
    """Start OAuth authorization code flow with PKCE and localhost redirect.

    Opens the default browser and blocks until the redirect is received or the
    timeout expires. Returns the token response from Google.
    """
    client_id, client_secret = _get_client_credentials()
    verifier, challenge = _generate_pkce_pair()
    port = _find_free_port()
    redirect_uri = f"http://127.0.0.1:{port}"
    state = secrets.token_urlsafe(16)

    _RedirectHandler.code = None
    _RedirectHandler.error = None
    _RedirectHandler.error_description = None

    server = HTTPServer(("127.0.0.1", port), _RedirectHandler)
    server_thread = Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    try:
        auth_url = (
            f"{AUTH_ENDPOINT}?"
            f"client_id={client_id}"
            f"&redirect_uri={redirect_uri}"
            f"&response_type=code"
            f"&scope={'+'.join(GEMINI_SCOPES)}"
            f"&state={state}"
            f"&code_challenge={challenge}"
            f"&code_challenge_method=S256"
            f"&access_type=offline"
            f"&prompt=consent"
        )

        print("\n🔐 Autenticação Google necessária.")
        print(f"   Abrindo navegador em: {redirect_uri}")
        print(f"   Se não abrir automaticamente, acesse:\n   {auth_url}\n")

        try:
            webbrowser.open(auth_url)
        except Exception:
            pass

        # Wait for the redirect.
        deadline = time.time() + timeout
        while time.time() < deadline:
            if _RedirectHandler.code is not None or _RedirectHandler.error is not None:
                break
            time.sleep(0.2)

        if _RedirectHandler.error is not None:
            raise RuntimeError(
                f"Google OAuth error: {_RedirectHandler.error} - {_RedirectHandler.error_description}"
            )
        if _RedirectHandler.code is None:
            raise RuntimeError("Google OAuth timeout: no redirect received.")

        code = _RedirectHandler.code

        response = requests.post(
            TOKEN_ENDPOINT,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
                "code_verifier": verifier,
            },
            timeout=30,
        )
        response.raise_for_status()
        token_data = response.json()

        credentials = {
            "access_token": token_data["access_token"],
            "refresh_token": token_data.get("refresh_token"),
            "token_type": token_data.get("token_type", "Bearer"),
            "expires_at": int(time.time()) + token_data.get("expires_in", 3600),
            "scope": token_data.get("scope", " ".join(GEMINI_SCOPES)),
        }
        _save_credentials(credentials)
        return credentials
    finally:
        server.shutdown()
        server.server_close()


def refresh_access_token(refresh_token: str) -> str:
    """Refresh the access token and update stored credentials."""
    client_id, client_secret = _get_client_credentials()
    response = requests.post(
        TOKEN_ENDPOINT,
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
        return start_authorization_flow()["access_token"]

    credentials = _load_stored_credentials()
    if credentials:
        access_token = credentials["access_token"]
        refresh_token = credentials.get("refresh_token")
        if credentials.get("expires_at", 0) <= time.time() + 60:
            if refresh_token:
                return refresh_access_token(refresh_token)
        else:
            return access_token

    return start_authorization_flow()["access_token"]


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
