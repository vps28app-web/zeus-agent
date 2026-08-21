"""Additional unit tests for zeus/tools/sandbox_client.py."""

import os
from unittest.mock import MagicMock, patch

from zeus.tools import sandbox_client as client


def test_current_user_session_reads_env():
    with patch.dict(os.environ, {"ZEUS_USER_ID": "user-1", "ZEUS_SESSION_ID": "sess-1"}, clear=False):
        uid, sid = client.current_user_session()
    assert uid == "user-1"
    assert sid == "sess-1"


def test_current_user_session_returns_none_when_missing():
    with patch.dict(os.environ, {"ZEUS_USER_ID": "", "ZEUS_SESSION_ID": ""}, clear=False):
        uid, sid = client.current_user_session()
    assert uid is None
    assert sid is None


@patch("requests.get")
def test_is_sandbox_available_true(mock_get):
    mock_get.return_value.status_code = 200
    assert client.is_sandbox_available("http://127.0.0.1:9876") is True


@patch("requests.get")
def test_is_sandbox_available_false_on_error(mock_get):
    import requests

    mock_get.side_effect = requests.RequestException("connection refused")
    assert client.is_sandbox_available("http://127.0.0.1:9876") is False


@patch("requests.get")
def test_health_check_success(mock_get):
    mock_get.return_value.status_code = 200
    mock_get.return_value.json.return_value = {"status": "ok"}
    mock_get.return_value.raise_for_status = MagicMock()
    result = client.health_check("http://127.0.0.1:9876")
    assert result["status"] == "ok"


@patch("requests.get")
def test_health_check_failure(mock_get):
    import requests

    mock_get.side_effect = requests.RequestException("down")
    result = client.health_check("http://127.0.0.1:9876")
    assert "error" in result


@patch("zeus.tools.sandbox_client.is_sandbox_available")
@patch("requests.post")
def test_run_sandboxed_command_success(mock_post, mock_available):
    mock_available.return_value = True
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = {"stdout": "hello", "stderr": "", "exit_code": 0}
    mock_post.return_value.raise_for_status = MagicMock()

    result = client.run_sandboxed_command("echo hello", timeout=5)
    assert result["stdout"] == "hello"
    assert result["exit_code"] == 0


@patch("zeus.tools.sandbox_client.is_sandbox_available")
def test_run_sandboxed_command_unavailable(mock_available):
    mock_available.return_value = False
    result = client.run_sandboxed_command("echo hello")
    assert "error" in result
    assert "not available" in result["error"]


@patch("zeus.tools.sandbox_client.is_sandbox_available")
@patch("requests.post")
def test_run_sandboxed_command_connection_error(mock_post, mock_available):
    import requests

    mock_available.return_value = True
    mock_post.side_effect = requests.ConnectionError("refused")
    result = client.run_sandboxed_command("echo hello")
    assert "error" in result
    assert "not available" in result["error"]
