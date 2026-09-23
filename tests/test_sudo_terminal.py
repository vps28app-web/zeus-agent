"""Tests for sudo password handling in run_terminal."""

from unittest.mock import MagicMock, patch

import pytest

from zeus.security.permissions import PermissionManager
from zeus.tools.terminal import _needs_sudo, _run_with_optional_sudo


def _fake_popen(stdout_text: str = "", stderr_text: str = "", returncode: int = 0):
    """Build a MagicMock Popen whose stdout/stderr yield the given lines then EOF."""
    proc = MagicMock()
    proc.returncode = returncode

    def _stream(text):
        mock_stream = MagicMock()
        mock_stream.readline.side_effect = list(text.splitlines(keepends=True)) + [""]
        return mock_stream

    proc.stdout = _stream(stdout_text)
    proc.stderr = _stream(stderr_text)
    proc.stdin = MagicMock()
    proc.wait.return_value = returncode
    return proc


def test_needs_sudo_detection():
    assert _needs_sudo("sudo apt install curl")
    assert _needs_sudo("cd /tmp && sudo make install")
    assert not _needs_sudo("echo hello")
    assert not _needs_sudo("sudoku")
    assert not _needs_sudo("echo sudo | grep foo")


def test_run_with_sudo_prompts_password():
    pm = PermissionManager(exec_level="allow")
    with patch.object(pm, "ask_password", return_value="secretpw") as ask:
        with patch("zeus.tools.terminal.subprocess.Popen") as mock_popen:
            mock_popen.return_value = _fake_popen(stdout_text="ok\n")
            result = _run_with_optional_sudo("sudo apt install curl", 30, None, pm)

    assert result["exit_code"] == 0
    assert "ok" in result["stdout"]
    # The password must not appear in the command string passed to subprocess.
    args, kwargs = mock_popen.call_args
    command_passed = args[0]
    assert "secretpw" not in command_passed
    # sudo must be rewritten to sudo -S so it reads password from stdin.
    assert "sudo -S" in command_passed


def test_run_without_sudo_no_prompt():
    pm = PermissionManager(exec_level="allow")
    with patch.object(pm, "ask_password") as ask:
        with patch("zeus.tools.terminal.subprocess.Popen") as mock_popen:
            mock_popen.return_value = _fake_popen(stdout_text="hi\n")
            _run_with_optional_sudo("echo hello", 30, None, pm)
    ask.assert_not_called()


def test_run_with_sudo_cancel_returns_error():
    pm = PermissionManager(exec_level="allow")
    with patch.object(pm, "ask_password", return_value=None):
        result = _run_with_optional_sudo("sudo apt install curl", 30, None, pm)
    assert result["exit_code"] == 1
    assert "senha sudo" in result["stderr"].lower()
