"""Unit tests for zeus/tools/sandbox.py."""

from unittest.mock import patch

from zeus.tools.sandbox import run_sandboxed


def test_run_sandboxed_success():
    with patch("zeus.tools.sandbox_client.current_user_session", return_value=("u1", "s1")):
        with patch("zeus.security.rate_limit.get_execution_limiter") as mock_limiter:
            mock_limiter.return_value.is_allowed.return_value = True
            with patch("zeus.tools.sandbox_client.run_sandboxed_command", return_value={"stdout": "ok"}):
                with patch("zeus.security.audit.get_audit_logger") as mock_audit:
                    result = run_sandboxed("echo ok")

    assert result["stdout"].strip() == "ok"
    mock_audit.return_value.log_execution.assert_called_once()


def test_run_sandboxed_rate_limited():
    with patch("zeus.tools.sandbox_client.current_user_session", return_value=("u1", "s1")):
        with patch("zeus.security.rate_limit.get_execution_limiter") as mock_limiter:
            mock_limiter.return_value.is_allowed.return_value = False
            result = run_sandboxed("echo ok")

    assert "error" in result
    assert "Rate limit" in result["error"]
