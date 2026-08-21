"""Unit tests for zeus/tools/code_execution.py."""

from unittest.mock import patch

from zeus.tools import code_execution
from zeus.tools.code_execution import execute_python, execute_shell_script


def test_execute_python_rate_limited():
    with patch("zeus.security.rate_limit.get_execution_limiter") as mock_limiter:
        with patch("zeus.tools.sandbox_client.current_user_session", return_value=("u1", "s1")):
            mock_limiter.return_value.is_allowed.return_value = False
            result = execute_python("print(1)")
    assert "error" in result
    assert "Rate limit" in result["error"]


def test_execute_python_permission_denied():
    with patch("zeus.security.rate_limit.get_execution_limiter") as mock_limiter:
        with patch("zeus.tools.sandbox_client.current_user_session", return_value=("u1", "s1")):
            mock_limiter.return_value.is_allowed.return_value = True
            with patch.object(code_execution._permissions, "can_run_sandboxed_python", return_value=False):
                result = execute_python("print(1)")
    assert "error" in result


def test_execute_python_unsafe_code():
    with patch("zeus.security.rate_limit.get_execution_limiter") as mock_limiter:
        with patch("zeus.tools.sandbox_client.current_user_session", return_value=("u1", "s1")):
            mock_limiter.return_value.is_allowed.return_value = True
            with patch.object(code_execution._permissions, "can_run_sandboxed_python", return_value=True):
                with patch("zeus.security.permissions.check_python_safety", return_value="unsafe import"):
                    result = execute_python("import os")
    assert "error" in result
    assert "Blocked" in result["error"]


def test_execute_python_success():
    with patch("zeus.security.rate_limit.get_execution_limiter") as mock_limiter:
        with patch("zeus.tools.sandbox_client.current_user_session", return_value=("u1", "s1")):
            mock_limiter.return_value.is_allowed.return_value = True
            with patch.object(code_execution._permissions, "can_run_sandboxed_python", return_value=True):
                with patch("zeus.security.permissions.check_python_safety", return_value=None):
                    with patch("zeus.tools.code_execution.run_sandboxed_command", return_value={"stdout": "42\n"}):
                        with patch("zeus.security.audit.get_audit_logger") as mock_audit:
                            result = execute_python("print(42)")

    assert result["stdout"].strip() == "42"
    mock_audit.return_value.log_execution.assert_called_once()


def test_execute_shell_script_rate_limited():
    with patch("zeus.security.rate_limit.get_execution_limiter") as mock_limiter:
        with patch("zeus.tools.sandbox_client.current_user_session", return_value=("u1", "s1")):
            mock_limiter.return_value.is_allowed.return_value = False
            result = execute_shell_script("echo hi")
    assert "error" in result
    assert "Rate limit" in result["error"]


def test_execute_shell_script_unsafe():
    with patch("zeus.security.rate_limit.get_execution_limiter") as mock_limiter:
        with patch("zeus.tools.sandbox_client.current_user_session", return_value=("u1", "s1")):
            mock_limiter.return_value.is_allowed.return_value = True
            with patch.object(code_execution._permissions, "can_run_sandboxed_shell", return_value=True):
                with patch("zeus.security.permissions.check_shell_safety", return_value="rm is dangerous"):
                    result = execute_shell_script("rm -rf /")
    assert "error" in result
    assert "Dangerous" in result["error"]


def test_execute_shell_script_success():
    with patch("zeus.security.rate_limit.get_execution_limiter") as mock_limiter:
        with patch("zeus.tools.sandbox_client.current_user_session", return_value=("u1", "s1")):
            mock_limiter.return_value.is_allowed.return_value = True
            with patch.object(code_execution._permissions, "can_run_sandboxed_shell", return_value=True):
                with patch("zeus.security.permissions.check_shell_safety", return_value=None):
                    with patch("zeus.tools.code_execution.run_sandboxed_command", return_value={"stdout": "hi\n"}):
                        with patch("zeus.security.audit.get_audit_logger"):
                            result = execute_shell_script("echo hi")

    assert result["stdout"].strip() == "hi"
