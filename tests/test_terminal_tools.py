"""Unit tests for background terminal tools in zeus/tools/terminal.py."""

import time

import pytest

from zeus.tools.terminal import (
    _permissions,
    command_status,
    run_background_command,
    run_terminal,
    terminate_command,
)


@pytest.fixture(autouse=True)
def allow_terminal_execution(monkeypatch):
    monkeypatch.setenv("ZEUS_EXECUTION_PERMISSION", "allow")
    _permissions.exec_level = "allow"
    _permissions.file_level = "unrestricted"
    _permissions.terminal_level = "unrestricted"


def test_run_terminal_with_cwd(tmp_path):
    sub = tmp_path / "subdir"
    sub.mkdir()
    (sub / "test.txt").write_text("hello from sub", encoding="utf-8")

    res = run_terminal(command="cat test.txt", cwd=str(sub))
    assert res.get("exit_code") == 0, f"Error in run_terminal: {res}"
    assert "hello from sub" in res["stdout"]


def test_run_background_command_and_status(tmp_path):
    res_bg = run_background_command(command="echo 'background test output'; sleep 0.2; echo 'done'", cwd=str(tmp_path))
    assert res_bg.get("status") == "started", f"Error in run_background_command: {res_bg}"
    cmd_id = res_bg["command_id"]
    assert cmd_id.startswith("cmd_")

    time.sleep(0.3)

    res_st = command_status(command_id=cmd_id)
    assert res_st["command_id"] == cmd_id
    assert any("background test output" in line for line in res_st["stdout"])

    res_term = terminate_command(command_id=cmd_id)
    assert res_term["status"] == "success"
