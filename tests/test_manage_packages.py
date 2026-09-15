"""Tests for manage_packages tool."""

from unittest.mock import patch

import pytest

from zeus.tools.manage_packages import manage_packages


@pytest.fixture(autouse=True)
def allow_terminal(monkeypatch):
    monkeypatch.setenv("ZEUS_EXECUTION_PERMISSION", "allow")


def test_manage_packages_requires_terminal_mode(monkeypatch):
    monkeypatch.setenv("ZEUS_EXECUTION_PERMISSION", "sandbox_only")
    result = manage_packages("apt list --installed")
    assert "error" in result
    assert "/mode terminal" in result["error"]


def test_manage_packages_blocks_unknown_manager():
    result = manage_packages("npm install foo")
    assert "error" in result
    assert "Package manager not allowed" in result["error"]


def test_manage_packages_allows_safe_apt():
    with patch("zeus.tools.manage_packages.subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "foo/stable"
        mock_run.return_value.stderr = ""
        result = manage_packages("apt list --installed")
    assert result["exit_code"] == 0
    assert result["stdout"] == "foo/stable"


def test_manage_packages_asks_confirmation_for_mutating():
    result = manage_packages("apt remove foo")
    assert "permission_required" in result
    assert result["permission_required"]["action"] == "manage_packages"
    assert "apt remove foo" in result["permission_required"]["command"]


def test_manage_packages_asks_confirmation_for_pip_install():
    result = manage_packages("pip install requests")
    assert "permission_required" in result


def test_manage_packages_asks_confirmation_for_flatpak_uninstall():
    result = manage_packages("flatpak uninstall com.example.App")
    assert "permission_required" in result


def test_manage_packages_executes_when_confirmed():
    with patch("zeus.tools.manage_packages.subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "ok"
        mock_run.return_value.stderr = ""
        result = manage_packages("apt remove foo", confirm=False)
    assert result["exit_code"] == 0
    assert result["stdout"] == "ok"


def test_manage_packages_blocks_dangerous_subcommand():
    result = manage_packages("apt dist-upgrade")
    # dist-upgrade is mutating -> needs confirmation
    assert "permission_required" in result

    result = manage_packages("apt moo")
    assert "error" in result
    assert "not allowed" in result["error"]


def test_manage_packages_rejects_shell_metacharacters():
    result = manage_packages("pip install requests; rm -rf /")
    assert "error" in result
    assert "metacharacters" in result["error"].lower()


def test_manage_packages_rejects_backtick():
    result = manage_packages("pip install requests `whoami`")
    assert "error" in result
    assert "metacharacters" in result["error"].lower()


def test_manage_packages_rejects_pipe():
    result = manage_packages("pip install requests | bash")
    assert "error" in result
    assert "metacharacters" in result["error"].lower()
