"""Extra tests for zeus/tools/terminal.py edge cases."""

import subprocess
from unittest import mock

import pytest

from zeus.security.permissions import PermissionManager
from zeus.tools import terminal


@pytest.fixture(autouse=True)
def reset_permissions(monkeypatch):
    monkeypatch.setenv("ZEUS_EXECUTION_MODE", "auto")
    terminal._permissions = PermissionManager(exec_level="allow")
    yield
    terminal._permissions = PermissionManager(exec_level="allow")


def test_run_terminal_no_longer_blocked_by_pattern():
    with mock.patch("zeus.security.rate_limit.get_execution_limiter") as mock_limiter:
        with mock.patch("zeus.tools.sandbox_client.current_user_session", return_value=("u1", "s1")):
            mock_limiter.return_value.is_allowed.return_value = True
            terminal._permissions = PermissionManager(exec_level="allow")
            with mock.patch("subprocess.run") as mock_run:
                mock_run.return_value.returncode = 0
                mock_run.return_value.stdout = ""
                mock_run.return_value.stderr = ""
                result = terminal.run_terminal("rm -rf /")
    assert result["exit_code"] == 0


def test_run_background_command_rate_limited():
    with mock.patch("zeus.security.rate_limit.get_execution_limiter") as mock_limiter:
        with mock.patch("zeus.tools.sandbox_client.current_user_session", return_value=("u1", "s1")):
            mock_limiter.return_value.is_allowed.return_value = False
            result = terminal.run_background_command("echo hi")
    assert "error" in result
    assert "Rate limit" in result["error"]


def test_run_background_command_no_longer_blocked_by_pattern():
    terminal._permissions = PermissionManager(exec_level="allow")
    result = terminal.run_background_command("rm -rf /")
    assert result.get("status") == "started"


def test_run_background_command_cwd_missing():
    result = terminal.run_background_command("echo hi", cwd="/nonexistent/path/xyz")
    assert "error" in result


def test_command_status_reads_output():
    result = terminal.run_background_command("echo 'line1'; echo 'line2' >&2")
    cmd_id = result["command_id"]

    import time
    time.sleep(0.3)

    status = terminal.command_status(cmd_id, max_lines=10)
    assert status["command_id"] == cmd_id
    assert any("line1" in line for line in status["stdout"])
    assert any("line2" in line for line in status["stderr"])


def test_command_status_with_closed_streams():
    result = terminal.run_background_command("echo hi")
    cmd_id = result["command_id"]

    import time
    time.sleep(0.3)

    entry = terminal._background_processes[cmd_id]
    entry["process"].stdout.close()
    entry["process"].stderr.close()

    status = terminal.command_status(cmd_id)
    assert status["command_id"] == cmd_id


def test_terminate_command_running_process():
    result = terminal.run_background_command("sleep 10")
    cmd_id = result["command_id"]

    term = terminal.terminate_command(cmd_id)
    assert term["status"] == "success"
    assert term["action"] == "terminated"


def test_terminate_command_process_lookup_error():
    fake_proc = mock.Mock(spec=subprocess.Popen)
    fake_proc.pid = 12345
    fake_proc.poll.return_value = None
    fake_proc.wait.return_value = None

    cmd_id = "cmd_lookup"
    terminal._background_processes[cmd_id] = {
        "command": "sleep 10",
        "process": fake_proc,
        "started_at": 0,
        "cwd": None,
        "stdout_lines": [],
        "stderr_lines": [],
    }

    with mock.patch("os.getpgid", side_effect=ProcessLookupError("no pgid")):
        term = terminal.terminate_command(cmd_id)

    assert term["status"] == "success"
    assert term["action"] == "terminated"


def test_terminate_command_wait_timeout_then_kill():
    fake_proc = mock.Mock(spec=subprocess.Popen)
    fake_proc.pid = 12345
    fake_proc.poll.return_value = None
    fake_proc.wait.side_effect = [Exception("timeout"), None]

    cmd_id = "cmd_wait_timeout"
    terminal._background_processes[cmd_id] = {
        "command": "sleep 10",
        "process": fake_proc,
        "started_at": 0,
        "cwd": None,
        "stdout_lines": [],
        "stderr_lines": [],
    }

    with mock.patch("os.getpgid", side_effect=[12345, Exception("dead")]):
        with mock.patch("os.killpg"):
            with mock.patch("os.kill") as mock_kill:
                term = terminal.terminate_command(cmd_id)

    assert term["status"] == "success"
    assert term["action"] == "terminated"
    mock_kill.assert_called_once()
