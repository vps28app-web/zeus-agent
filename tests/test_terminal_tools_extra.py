"""Additional unit tests for zeus/tools/terminal.py."""

from unittest.mock import patch

from zeus.security.permissions import PermissionManager
from zeus.tools import terminal


def test_run_terminal_rate_limited():
    with patch("zeus.security.rate_limit.get_execution_limiter") as mock_limiter:
        with patch("zeus.tools.sandbox_client.current_user_session", return_value=("u1", "s1")):
            mock_limiter.return_value.is_allowed.return_value = False
            result = terminal.run_terminal("echo hi")
    assert "error" in result
    assert "Rate limit" in result["error"]


def test_run_terminal_permission_denied():
    with patch("zeus.security.rate_limit.get_execution_limiter") as mock_limiter:
        with patch("zeus.tools.sandbox_client.current_user_session", return_value=("u1", "s1")):
            mock_limiter.return_value.is_allowed.return_value = True
            terminal._permissions = PermissionManager(exec_level="deny")
            result = terminal.run_terminal("echo hi")
    assert "error" in result
    assert "denied" in result["error"]


def test_run_terminal_unsafe_denied_without_confirmation():
    with patch("zeus.security.rate_limit.get_execution_limiter") as mock_limiter:
        with patch("zeus.tools.sandbox_client.current_user_session", return_value=("u1", "s1")):
            mock_limiter.return_value.is_allowed.return_value = True
            terminal._permissions = PermissionManager(exec_level="allow")  # execution_mode defaults to "terminal"
            result = terminal.run_terminal("rm -rf /")
    assert "error" in result
    assert "denied" in result["error"].lower()


def test_run_terminal_unsafe_authorized_executes():
    with patch("zeus.security.rate_limit.get_execution_limiter") as mock_limiter:
        with patch("zeus.tools.sandbox_client.current_user_session", return_value=("u1", "s1")):
            mock_limiter.return_value.is_allowed.return_value = True
            pm = PermissionManager(exec_level="allow", confirm_callback=lambda msg: "yes")
            terminal._permissions = pm
            with patch("subprocess.run") as mock_run:
                mock_run.return_value.returncode = 0
                mock_run.return_value.stdout = ""
                mock_run.return_value.stderr = ""
                result = terminal.run_terminal("rm -rf /")
    assert result["exit_code"] == 0
    mock_run.assert_called_once()


def test_run_terminal_unsafe_blocked_in_auto_mode():
    with patch("zeus.security.rate_limit.get_execution_limiter") as mock_limiter:
        with patch("zeus.tools.sandbox_client.current_user_session", return_value=("u1", "s1")):
            mock_limiter.return_value.is_allowed.return_value = True
            with patch.dict("os.environ", {"ZEUS_EXECUTION_MODE": "auto"}, clear=False):
                terminal._permissions = PermissionManager(exec_level="allow")
                result = terminal.run_terminal("rm -rf /")
    assert "error" in result
    assert "Dangerous" in result["error"]


def test_run_terminal_cwd_missing():
    with patch("zeus.security.rate_limit.get_execution_limiter") as mock_limiter:
        with patch("zeus.tools.sandbox_client.current_user_session", return_value=("u1", "s1")):
            mock_limiter.return_value.is_allowed.return_value = True
            terminal._permissions = PermissionManager(exec_level="allow")
            result = terminal.run_terminal("echo hi", cwd="/nonexistent/path/xyz")
    assert "error" in result


def test_run_terminal_success(tmp_path):
    with patch("zeus.security.rate_limit.get_execution_limiter") as mock_limiter:
        with patch("zeus.tools.sandbox_client.current_user_session", return_value=("u1", "s1")):
            mock_limiter.return_value.is_allowed.return_value = True
            terminal._permissions = PermissionManager(exec_level="allow")
            result = terminal.run_terminal("echo hello", cwd=str(tmp_path))
    assert result["exit_code"] == 0
    assert "hello" in result["stdout"]


def test_run_background_command_permission_denied():
    terminal._permissions = PermissionManager(exec_level="deny")
    result = terminal.run_background_command("echo hi")
    assert "error" in result


def test_run_background_command_success(tmp_path):
    terminal._permissions = PermissionManager(exec_level="allow")
    result = terminal.run_background_command("sleep 0.1", cwd=str(tmp_path))
    assert result["status"] == "started"
    assert "command_id" in result

    cmd_id = result["command_id"]
    status = terminal.command_status(cmd_id)
    assert status["command_id"] == cmd_id
    assert status["status"] in ("running", "finished")

    term = terminal.terminate_command(cmd_id)
    assert term["status"] == "success"


def test_command_status_unknown():
    result = terminal.command_status("cmd_nonexistent")
    assert "error" in result


def test_terminate_command_unknown():
    result = terminal.terminate_command("cmd_nonexistent")
    assert "error" in result


def test_terminate_command_already_finished():
    terminal._permissions = PermissionManager(exec_level="allow")
    result = terminal.run_background_command("echo done")
    cmd_id = result["command_id"]

    import time
    time.sleep(0.3)

    term = terminal.terminate_command(cmd_id)
    assert term["action"] == "already_finished"
