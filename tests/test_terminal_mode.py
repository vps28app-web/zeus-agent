"""Tests for terminal mode confirmation flow."""

from unittest.mock import patch

import pytest

from zeus.security.permissions import (
    PermissionManager,
    get_global_permission_manager,
    set_global_permission_manager,
)
from zeus.tools.terminal import run_terminal


@pytest.fixture
def terminal_pm(monkeypatch):
    monkeypatch.setenv("ZEUS_EXECUTION_PERMISSION", "allow")
    monkeypatch.setenv("ZEUS_EXECUTION_MODE", "terminal")
    previous = get_global_permission_manager()
    pm = PermissionManager(exec_level="allow")
    set_global_permission_manager(pm)
    yield pm
    set_global_permission_manager(previous)


def test_run_terminal_requires_confirmation(terminal_pm, monkeypatch):
    # User denies
    with patch.object(terminal_pm, "confirm_tool", return_value=False):
        result = run_terminal("echo test")
    assert "error" in result
    assert "denied" in result["error"].lower()


def test_run_terminal_executes_when_confirmed(terminal_pm, monkeypatch):
    with patch.object(terminal_pm, "confirm_tool", return_value=True):
        result = run_terminal("echo hello-terminal")
    assert result["exit_code"] == 0
    assert "hello-terminal" in result["stdout"]
