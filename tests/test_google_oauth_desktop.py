"""Unit tests for zeus/core/google_oauth_desktop.py."""

import json
import os
import time
from unittest.mock import MagicMock, patch

import pytest

from zeus.core import google_oauth_desktop as oauth


def test_generate_pkce_pair():
    verifier, challenge = oauth._generate_pkce_pair()
    assert verifier != challenge
    assert len(verifier) > 20
    assert len(challenge) > 20
    # Verify S256 challenge
    import base64
    import hashlib

    expected = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest())
        .rstrip(b"=")
        .decode("ascii")
    )
    assert challenge == expected


def test_load_save_credentials(tmp_path, monkeypatch):
    monkeypatch.setattr(oauth, "_credential_path", lambda: tmp_path / "creds.json")
    assert oauth._load_stored_credentials() is None
    data = {"access_token": "abc", "expires_at": 123}
    oauth._save_credentials(data)
    loaded = oauth._load_stored_credentials()
    assert loaded == data


def test_get_client_credentials_missing():
    with patch.dict(os.environ, {"GOOGLE_OAUTH_CLIENT_ID": "", "GOOGLE_OAUTH_CLIENT_SECRET": ""}, clear=False):
        with pytest.raises(RuntimeError, match="GOOGLE_OAUTH_CLIENT_ID"):
            oauth._get_client_credentials()


def test_get_client_credentials_present():
    env = {"GOOGLE_OAUTH_CLIENT_ID": "id", "GOOGLE_OAUTH_CLIENT_SECRET": "secret"}
    with patch.dict(os.environ, env, clear=False):
        assert oauth._get_client_credentials() == ("id", "secret")


def test_has_valid_credentials(tmp_path, monkeypatch):
    monkeypatch.setattr(oauth, "_credential_path", lambda: tmp_path / "creds.json")
    assert oauth.has_valid_credentials() is False
    oauth._save_credentials({"access_token": "x", "expires_at": int(time.time()) + 3600})
    assert oauth.has_valid_credentials() is True


def test_revoke_credentials(tmp_path, monkeypatch):
    monkeypatch.setattr(oauth, "_credential_path", lambda: tmp_path / "creds.json")
    oauth._save_credentials({"access_token": "x"})
    assert tmp_path.joinpath("creds.json").exists()
    oauth.revoke_credentials()
    assert not tmp_path.joinpath("creds.json").exists()


@patch("zeus.core.google_oauth_desktop.requests.post")
@patch("zeus.core.google_oauth_desktop.webbrowser.open")
@patch("zeus.core.google_oauth_desktop.HTTPServer")
def test_start_authorization_flow_success(mock_server_cls, mock_browser, mock_post, tmp_path, monkeypatch):
    monkeypatch.setattr(oauth, "_credential_path", lambda: tmp_path / "creds.json")
    mock_server = MagicMock()
    mock_server_cls.return_value = mock_server

    # Simulate redirect handler receiving a code.
    captured_code = "auth-code-123"

    def simulate_serve():
        oauth._RedirectHandler.code = captured_code

    mock_server.serve_forever.side_effect = simulate_serve

    mock_response = MagicMock()
    mock_response.json.return_value = {
        "access_token": "access-123",
        "refresh_token": "refresh-123",
        "expires_in": 3600,
        "token_type": "Bearer",
    }
    mock_response.raise_for_status.return_value = None
    mock_post.return_value = mock_response

    env = {
        "GOOGLE_OAUTH_CLIENT_ID": "client-id.apps.googleusercontent.com",
        "GOOGLE_OAUTH_CLIENT_SECRET": "secret",
    }
    with patch.dict(os.environ, env, clear=False):
        with patch.object(oauth, "_find_free_port", return_value=54321):
            result = oauth.start_authorization_flow(timeout=2)

    assert result["access_token"] == "access-123"
    assert result["refresh_token"] == "refresh-123"
    assert mock_browser.called

    call_args = mock_post.call_args.kwargs["data"]
    assert call_args["grant_type"] == "authorization_code"
    assert call_args["code"] == captured_code
    assert call_args["redirect_uri"] == "http://127.0.0.1:54321"
    assert "code_verifier" in call_args


@patch("zeus.core.google_oauth_desktop.requests.post")
def test_refresh_access_token(mock_post, tmp_path, monkeypatch):
    monkeypatch.setattr(oauth, "_credential_path", lambda: tmp_path / "creds.json")
    oauth._save_credentials({"access_token": "old", "refresh_token": "rt", "token_type": "Bearer"})

    mock_response = MagicMock()
    mock_response.json.return_value = {
        "access_token": "new-access",
        "expires_in": 3600,
        "token_type": "Bearer",
    }
    mock_response.raise_for_status.return_value = None
    mock_post.return_value = mock_response

    env = {
        "GOOGLE_OAUTH_CLIENT_ID": "client-id.apps.googleusercontent.com",
        "GOOGLE_OAUTH_CLIENT_SECRET": "secret",
    }
    with patch.dict(os.environ, env, clear=False):
        token = oauth.refresh_access_token("rt")

    assert token == "new-access"
    loaded = json.loads((tmp_path / "creds.json").read_text())
    assert loaded["access_token"] == "new-access"
    assert loaded["expires_at"] > int(time.time())


@patch("zeus.core.google_oauth_desktop._load_stored_credentials")
def test_get_access_token_uses_stored_token(mock_load):
    future = int(time.time()) + 3600
    mock_load.return_value = {"access_token": "valid", "expires_at": future}
    assert oauth.get_access_token() == "valid"
