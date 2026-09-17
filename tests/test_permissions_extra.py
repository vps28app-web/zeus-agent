"""Additional unit tests for zeus/security/permissions.py."""

from pathlib import Path

import pytest

from zeus.security.permissions import (
    PermissionManager,
    PermissionRequired,
    check_python_safety,
    check_shell_safety,
)


def test_permission_manager_invalid_levels_default():
    pm = PermissionManager(exec_level="invalid", file_level="invalid")
    assert pm.exec_level == "sandbox_only"
    assert pm.file_level == "read_only"


def test_can_read_file_true():
    pm = PermissionManager(file_level="read_only")
    assert pm.can_read_file(Path("/any")) is True


def test_can_write_file_unrestricted():
    pm = PermissionManager(file_level="unrestricted")
    assert pm.can_write_file(Path("/etc/passwd")) is True


def test_can_write_file_project_only_outside(tmp_path):
    pm = PermissionManager(project_dir=tmp_path, file_level="project_only")
    assert pm.can_write_file(Path("/tmp/outside.txt")) is False


def test_can_delete_file_project_only_inside(tmp_path):
    pm = PermissionManager(project_dir=tmp_path, file_level="project_only")
    f = tmp_path / "x.txt"
    f.write_text("x", encoding="utf-8")
    assert pm.can_delete_file(f) is True


def test_denied_message():
    pm = PermissionManager(exec_level="deny")
    msg = pm.denied_message("terminal")
    assert "Execution denied" in msg
    assert "deny" in msg


def test_ensure_write_allowed_raises():
    pm = PermissionManager(file_level="read_only")
    with pytest.raises(PermissionRequired):
        pm.ensure_write_allowed(Path("/tmp/x.txt"))


def test_confirm_callback_returns_false():
    pm = PermissionManager(file_level="read_only", confirm_callback=lambda m: False)
    assert pm.confirm_action("write", Path("/tmp/x.txt")) is False


def test_confirm_callback_yes():
    pm = PermissionManager(file_level="read_only", confirm_callback=lambda m: "yes")
    assert pm.confirm_action("write", Path("/tmp/x.txt")) is True


def test_confirm_callback_always():
    pm = PermissionManager(file_level="read_only", confirm_callback=lambda m: "always")
    assert pm.confirm_action("write", Path("/tmp/x.txt")) is True
    assert pm.confirm_action("write", Path("/tmp/y.txt")) is True


def test_confirm_callback_persist(tmp_path, monkeypatch):
    monkeypatch.setenv("ZEUS_HOME", str(tmp_path))
    pm = PermissionManager(file_level="read_only", confirm_callback=lambda m: "persist", user_id="u1")
    assert pm.confirm_action("write", Path("/tmp/x.txt")) is True


def test_grant_permission_once_and_reuse():
    pm = PermissionManager(file_level="read_only")
    pm.grant_permission("write", Path("/tmp/x.txt"), scope="once")
    assert pm.confirm_action("write", Path("/tmp/x.txt")) is True


def test_grant_permission_always():
    pm = PermissionManager(file_level="read_only")
    pm.grant_permission("write", Path("/tmp/x.txt"), scope="always")
    assert pm.confirm_action("write", Path("/tmp/y.txt")) is True


def test_normalize_confirmation_answer():
    pm = PermissionManager()
    assert pm._normalize_confirmation_answer("Y") == "once"
    assert pm._normalize_confirmation_answer("always") == "always"
    assert pm._normalize_confirmation_answer("persist") == "persist"
    assert pm._normalize_confirmation_answer("n") == "deny"
    assert pm._normalize_confirmation_answer(None) is None


def test_is_inside_project_traversal(tmp_path):
    pm = PermissionManager(project_dir=tmp_path, file_level="project_only")
    outside = tmp_path / ".." / "outside.txt"
    assert pm._is_inside_project(outside) is False


def test_check_shell_safety_no_longer_blocks_by_pattern():
    # Human confirmation is now the only gate in terminal mode.
    assert check_shell_safety("rm -rf /") is None
    assert check_shell_safety("echo hello") is None


def test_check_python_safety_blocks_imports():
    assert "Blocked Python imports" in check_python_safety("import os")
    assert check_python_safety("print('hello')") is None


def test_check_python_safety_blocks_dynamic():
    assert "Blocked Python operations" in check_python_safety("eval('1+1')")


def test_check_python_safety_syntax_error():
    assert "syntax error" in check_python_safety("def foo(")


def test_check_python_safety_no_install():
    assert "Package installation" in check_python_safety("# pip install x\nx=1", allow_install=False)
