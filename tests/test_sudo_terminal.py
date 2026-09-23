"""Tests for sudo password handling in run_terminal."""

from unittest.mock import patch

import pytest

from zeus.security.permissions import PermissionManager, set_global_permission_manager
from zeus.tools.terminal import _needs_sudo, _run_with_optional_sudo


def test_needs_sudo_detection():
    assert _needs_sudo("sudo apt install curl")
    assert _needs_sudo("cd /tmp && sudo make install")
    assert not _needs_sudo("echo hello")
    assert not _needs_sudo("sudoku")
    assert not _needs_sudo("echo sudo | grep foo")


def test_run_with_sudo_prompts_password():
    pm = PermissionManager(exec_level="allow")
    with patch.object(pm, "ask_password", return_value="secretpw") as ask:
        with patch("zeus.tools.terminal.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = "ok\n"
            mock_run.return_value.stderr = ""
            result = _run_with_optional_sudo("sudo apt install curl", 30, None, pm)

    assert result["exit_code"] == 0
    assert "ok" in result["stdout"]
    # The password must not appear in the command string passed to subprocess.
    args, kwargs = mock_run.call_args
    command_passed = args[0]
    assert "secretpw" not in command_passed
    # sudo must be rewritten to sudo -S so it reads password from stdin.
    assert "sudo -S" in command_passed


def test_run_without_sudo_no_prompt():
    pm = PermissionManager(exec_level="allow")
    with patch.object(pm, "ask_password") as ask:
        with patch("zeus.tools.terminal.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = "hi\n"
            mock_run.return_value.stderr = ""
            _run_with_optional_sudo("echo hello", 30, None, pm)
    ask.assert_not_called()


def test_run_with_sudo_cancel_returns_error():
    pm = PermissionManager(exec_level="allow")
    with patch.object(pm, "ask_password", return_value=None):
        result = _run_with_optional_sudo("sudo apt install curl", 30, None, pm)
    assert result["exit_code"] == 1
    assert "senha sudo" in result["stderr"].lower()
