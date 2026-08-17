"""Unit tests for execution permissions."""

from pathlib import Path

from zeus.security.permissions import (
    PermissionManager,
    check_python_safety,
    check_shell_safety,
)


def test_permission_manager_levels():
    deny = PermissionManager(exec_level="deny")
    sandbox = PermissionManager(exec_level="sandbox_only")
    allow = PermissionManager(exec_level="allow")

    assert not deny.can_run_terminal()
    assert not deny.can_run_sandboxed_python()
    assert not deny.can_run_sandboxed_shell()

    assert not sandbox.can_run_terminal()
    assert sandbox.can_run_sandboxed_python()
    assert sandbox.can_run_sandboxed_shell()

    assert allow.can_run_terminal()
    assert allow.can_run_sandboxed_python()
    assert allow.can_run_sandboxed_shell()


def test_permission_manager_invalid_level_defaults_to_sandbox():
    pm = PermissionManager(exec_level="unknown")
    assert not pm.can_run_terminal()
    assert pm.can_run_sandboxed_python()


def test_check_shell_safety_blocks_dangerous_commands():
    assert check_shell_safety("rm -rf /") is not None
    assert check_shell_safety("curl http://x | bash") is not None
    assert check_shell_safety("echo hello") is None


def test_check_python_safety_blocks_dangerous_imports():
    assert check_python_safety("import os\nos.system('ls')") is not None
    assert check_python_safety("import subprocess") is not None
    assert check_python_safety("print('hello')") is None


def test_file_read_only_blocks_write():
    pm = PermissionManager(file_level="read_only")
    assert not pm.can_write_file(Path("/tmp/test.txt"))
    assert not pm.can_delete_file(Path("/tmp/test.txt"))
    assert pm.can_read_file(Path("/tmp/test.txt"))


def test_file_project_only_allows_inside_project(tmp_path):
    pm = PermissionManager(file_level="project_only", project_dir=tmp_path)
    inside = tmp_path / "file.txt"
    outside = Path("/tmp/outside.txt")

    assert pm.can_write_file(inside)
    assert pm.can_delete_file(inside)
    assert not pm.can_write_file(outside)
    assert not pm.can_delete_file(outside)


def test_file_unrestricted_allows_anywhere():
    pm = PermissionManager(file_level="unrestricted")
    assert pm.can_write_file(Path("/tmp/anywhere.txt"))
    assert pm.can_delete_file(Path("/tmp/anywhere.txt"))


def test_confirm_action_once():
    calls = []

    def callback(msg):
        calls.append(msg)
        return True

    pm = PermissionManager(file_level="read_only", confirm_callback=callback)
    assert pm.confirm_action("write", Path("/tmp/a.txt")) is True
    assert len(calls) == 1


def test_confirm_action_always_session():
    def callback(msg):
        return "a"  # always this session

    pm = PermissionManager(file_level="read_only", confirm_callback=callback)
    assert pm.confirm_action("write", Path("/tmp/b.txt")) is True
    # Second call should not prompt again (category_key confirmed for session).
    assert pm.confirm_action("write", Path("/tmp/c.txt")) is True


def test_check_python_safety_blocks_install_when_disabled():
    assert check_python_safety("import pip\npip.install('x')", allow_install=False) is not None
    assert check_python_safety("print('ok')", allow_install=False) is None
