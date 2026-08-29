"""Unit tests for zeus/core/google_oauth.py."""

import time
from unittest.mock import MagicMock, patch

import pytest

from zeus.core import google_oauth


@pytest.fixture(autouse=True)
def _isolate_credentials(tmp_path, monkeypatch):
    """Use a temporary credentials file for every test."""
    monkeypatch.setattr(google_oauth, "_credential_path", lambda: tmp_path / "google_creds.json")
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "test-client-secret")


@patch("requests.post")
@patch("webbrowser.open")
def test_start_device_flow_stores_credentials(mock_browser, mock_post, monkeypatch):
    mock_post.return_value.raise_for_status = MagicMock()
    mock_post.return_value.json.side_effect = [
        {
            "verification_url": "https://www.google.com/device",
            "user_code": "ABCD-EFGH",
            "device_code": "dev-code-123",
            "expires_in": 1800,
            "interval": 1,
        },
        {
            "access_token": "access-token-xyz",
            "refresh_token": "refresh-token-abc",
            "expires_in": 3600,
            "token_type": "Bearer",
            "scope": "test-scope",
        },
    ]
    monkeypatch.setattr(google_oauth, "_poll_for_token", lambda *args, **kwargs: {
        "access_token": "access-token-xyz",
        "refresh_token": "refresh-token-abc",
        "expires_in": 3600,
        "token_type": "Bearer",
        "scope": "test-scope",
    })

    credentials = google_oauth.start_device_flow()

    assert credentials["access_token"] == "access-token-xyz"
    assert credentials["refresh_token"] == "refresh-token-abc"
    assert credentials["token_type"] == "Bearer"
    assert credentials["expires_at"] > time.time()
    assert google_oauth._credential_path().exists()


@patch("requests.post")
def test_refresh_access_token_updates_credentials(mock_post, monkeypatch):
    stored = {
        "access_token": "old-token",
        "refresh_token": "refresh-token-abc",
        "expires_at": int(time.time()) - 100,
        "token_type": "Bearer",
    }
    google_oauth._save_credentials(stored)

    mock_response = MagicMock()
    mock_response.json.return_value = {
        "access_token": "new-token-123",
        "expires_in": 3600,
        "token_type": "Bearer",
    }
    mock_response.raise_for_status = MagicMock()
    mock_post.return_value = mock_response

    token = google_oauth.refresh_access_token("refresh-token-abc")

    assert token == "new-token-123"
    loaded = google_oauth._load_stored_credentials()
    assert loaded is not None
    assert loaded["access_token"] == "new-token-123"
    assert loaded["expires_at"] > time.time()


def test_get_access_token_uses_stored_valid_token(monkeypatch):
    stored = {
        "access_token": "valid-token",
        "expires_at": int(time.time()) + 3600,
    }
    google_oauth._save_credentials(stored)

    with patch.object(google_oauth, "start_device_flow") as mock_flow:
        token = google_oauth.get_access_token()

    assert token == "valid-token"
    mock_flow.assert_not_called()


def test_get_access_token_refreshes_expired_token_when_refresh_available(monkeypatch):
    stored = {
        "access_token": "expired-token",
        "refresh_token": "refresh-token-abc",
        "expires_at": int(time.time()) - 100,
    }
    google_oauth._save_credentials(stored)

    with patch.object(google_oauth, "refresh_access_token", return_value="refreshed-token") as mock_refresh:
        with patch.object(google_oauth, "start_device_flow") as mock_flow:
            token = google_oauth.get_access_token()

    assert token == "refreshed-token"
    mock_refresh.assert_called_once_with("refresh-token-abc")
    mock_flow.assert_not_called()


def test_revoke_credentials_removes_file():
    google_oauth._save_credentials({"access_token": "x"})
    assert google_oauth._credential_path().exists()
    google_oauth.revoke_credentials()
    assert not google_oauth._credential_path().exists()


def test_has_valid_credentials_true_and_false():
    assert not google_oauth.has_valid_credentials()
    google_oauth._save_credentials({"access_token": "x", "expires_at": int(time.time()) + 3600})
    assert google_oauth.has_valid_credentials()
    google_oauth.revoke_credentials()
    assert not google_oauth.has_valid_credentials()


def test_missing_client_credentials_raises(monkeypatch):
    monkeypatch.delenv("GOOGLE_OAUTH_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_OAUTH_CLIENT_SECRET", raising=False)
    with pytest.raises(RuntimeError, match="GOOGLE_OAUTH_CLIENT_ID"):
        google_oauth._get_client_credentials()
