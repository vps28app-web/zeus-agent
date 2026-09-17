"""Extra tests for zeus/security/permissions.py edge cases."""

from pathlib import Path
from unittest import mock

import pytest

from zeus.security.permissions import (
    PermissionManager,
    PermissionRequired,
    check_python_safety,
    check_shell_safety,
    get_global_permission_manager,
    set_global_permission_manager,
)


class TestPermissionManagerProperties:
    def test_invalid_exec_level_defaults_to_sandbox_only(self, monkeypatch):
        monkeypatch.setenv("ZEUS_EXECUTION_PERMISSION", "invalid")
        pm = PermissionManager()
        assert pm.exec_level == "sandbox_only"

    def test_invalid_file_level_defaults_to_read_only(self, monkeypatch):
        monkeypatch.setenv("ZEUS_FILE_PERMISSION", "invalid")
        pm = PermissionManager()
        assert pm.file_level == "read_only"

    def test_exec_level_setter(self):
        pm = PermissionManager()
        pm.exec_level = "Allow"
        assert pm.exec_level == "allow"

    def test_file_level_setter(self):
        pm = PermissionManager()
        pm.file_level = "Project_Only"
        assert pm.file_level == "project_only"

    def test_dry_run_property(self, monkeypatch):
        monkeypatch.setenv("ZEUS_DRY_RUN", "1")
        pm = PermissionManager()
        assert pm.dry_run is True

    def test_read_only_property(self, monkeypatch):
        monkeypatch.setenv("ZEUS_READ_ONLY", "true")
        pm = PermissionManager()
        assert pm.read_only is True

    def test_execution_mode_invalid_defaults_to_terminal(self, monkeypatch):
        monkeypatch.setenv("ZEUS_EXECUTION_MODE", "unknown")
        pm = PermissionManager()
        assert pm.execution_mode == "terminal"


class TestToolRiskAndConfirmation:
    def test_classify_tool_risk_empty_command(self):
        pm = PermissionManager()
        assert pm.classify_tool_risk("run_terminal", {"command": "  "}) == "none"

    def test_classify_tool_risk_medium_for_all_terminal_commands(self):
        pm = PermissionManager()
        # All terminal commands are medium risk so the user is asked for
        # confirmation in terminal mode. No command is hard-blocked by pattern.
        assert pm.classify_tool_risk("run_terminal", {"command": "sudo apt update"}) == "medium"
        assert pm.classify_tool_risk("run_terminal", {"command": "git push origin main"}) == "medium"
        assert pm.classify_tool_risk("run_terminal", {"command": "rm -rf /"}) == "medium"

    def test_classify_tool_risk_terminate_low(self):
        pm = PermissionManager()
        assert pm.classify_tool_risk("terminate_command", {}) == "low"

    def test_classify_tool_risk_manage_packages_remove(self):
        pm = PermissionManager()
        assert pm.classify_tool_risk("manage_packages", {"operation": "remove"}) == "high"

    def test_classify_tool_risk_manage_packages_install(self):
        pm = PermissionManager()
        assert pm.classify_tool_risk("manage_packages", {"operation": "install"}) == "medium"

    def test_classify_tool_risk_manage_packages_unknown(self):
        pm = PermissionManager()
        assert pm.classify_tool_risk("manage_packages", {"operation": "list"}) == "low"

    def test_classify_tool_risk_git_reset_high(self):
        pm = PermissionManager()
        assert pm.classify_tool_risk("git_reset", {}) == "high"

    def test_classify_tool_risk_git_push_medium(self):
        pm = PermissionManager()
        assert pm.classify_tool_risk("git_push", {}) == "medium"

    def test_classify_tool_risk_unknown_tool(self):
        pm = PermissionManager()
        assert pm.classify_tool_risk("unknown_tool", {}) == "none"

    def test_is_tool_allowed_read_only_blocks(self, monkeypatch):
        monkeypatch.setenv("ZEUS_READ_ONLY", "1")
        pm = PermissionManager()
        assert pm.is_tool_allowed("write_file") is False
        assert pm.is_tool_allowed("read_file") is True

    def test_is_confirmation_required_auto_mode(self, monkeypatch):
        monkeypatch.setenv("ZEUS_EXECUTION_MODE", "auto")
        pm = PermissionManager()
        assert pm.is_confirmation_required("run_terminal", {"command": "rm -rf /"}) is False

    def test_is_confirmation_required_low_risk(self):
        pm = PermissionManager()
        assert pm.is_confirmation_required("terminate_command", {}) is False


class TestConfirmTool:
    def test_confirm_tool_once(self):
        pm = PermissionManager(confirm_callback=lambda _: True)
        assert pm.confirm_tool("run_terminal", {"command": "ls"}) is True

    def test_confirm_tool_deny(self):
        pm = PermissionManager(confirm_callback=lambda _: False)
        assert pm.confirm_tool("run_terminal", {"command": "ls"}) is False

    def test_confirm_tool_always(self):
        def always(_):
            return "always"
        pm = PermissionManager(confirm_callback=always)
        assert pm.confirm_tool("run_terminal", {"command": "ls"}) is True
        assert "tool:run_terminal:*" in pm._confirmed_actions

    def test_confirm_tool_once_already_confirmed(self):
        pm = PermissionManager(confirm_callback=lambda _: True)
        pm._once_confirmed_actions.add("tool:run_terminal:ls")
        assert pm.confirm_tool("run_terminal", {"command": "ls"}) is True

    def test_confirm_tool_persistent_loaded(self):
        pm = PermissionManager(confirm_callback=lambda _: False)
        with mock.patch.object(pm, "_load_persistent_confirmations", return_value={"tool:run_terminal:*"}):
            assert pm.confirm_tool("run_terminal", {"command": "ls"}) is True


class TestFormatAndSignature:
    def test_tool_signature_terminal(self):
        pm = PermissionManager()
        assert pm._tool_signature("run_terminal", {"command": "ls"}) == "ls"

    def test_tool_signature_manage_packages(self):
        pm = PermissionManager()
        assert pm._tool_signature("manage_packages", {"operation": "install", "package_name": "pytest"}) == "install:pytest"

    def test_tool_signature_git(self):
        pm = PermissionManager()
        assert pm._tool_signature("git_push", {"args": "origin main"}) == "origin main"

    def test_format_tool_summary_terminal(self):
        pm = PermissionManager()
        assert pm._format_tool_summary("run_terminal", {"command": "ls"}) == "ls"

    def test_format_tool_summary_terminate(self):
        pm = PermissionManager()
        assert pm._format_tool_summary("terminate_command", {"command_id": "cmd_123"}) == "command_id=cmd_123"


class TestFileSystemPermissions:
    def test_is_inside_project_with_traversal(self, tmp_path):
        pm = PermissionManager(project_dir=tmp_path)
        outside = tmp_path / ".." / "outside.txt"
        assert pm._is_inside_project(outside) is False

    def test_is_inside_project_with_symlink_outside(self, tmp_path):
        pm = PermissionManager(project_dir=tmp_path)
        real_outside = tmp_path.parent / "real_outside.txt"
        real_outside.write_text("x")
        symlink = tmp_path / "link.txt"
        symlink.symlink_to(real_outside)
        assert pm._is_inside_project(symlink) is False

    def test_can_write_file_read_only(self):
        pm = PermissionManager(file_level="read_only")
        assert pm.can_write_file(Path("/tmp/x")) is False

    def test_can_write_file_unrestricted(self):
        pm = PermissionManager(file_level="unrestricted")
        assert pm.can_write_file(Path("/tmp/x")) is True

    def test_ensure_write_allowed_raises(self, tmp_path):
        pm = PermissionManager(file_level="read_only", confirm_callback=lambda _: False)
        with pytest.raises(PermissionRequired):
            pm.ensure_write_allowed(tmp_path / "x.txt")

    def test_ensure_delete_allowed_raises(self, tmp_path):
        pm = PermissionManager(file_level="read_only", confirm_callback=lambda _: False)
        with pytest.raises(PermissionRequired):
            pm.ensure_delete_allowed(tmp_path / "x.txt")


class TestGrantPermission:
    def test_grant_permission_once(self):
        pm = PermissionManager()
        pm.grant_permission("write", Path("/tmp/x"), scope="once")
        assert any("write:" in key for key in pm._once_confirmed_actions)

    def test_grant_permission_always(self):
        pm = PermissionManager()
        pm.grant_permission("write", Path("/tmp/x"), scope="always")
        assert "write:*" in pm._confirmed_actions

    def test_grant_permission_persist(self):
        pm = PermissionManager()
        with mock.patch.object(pm, "_save_persistent_confirmation") as mock_save:
            pm.grant_permission("write", Path("/tmp/x"), scope="persist")
        assert "write:*" in pm._confirmed_actions
        mock_save.assert_called_once_with("write:*")


class TestConfirmAction:
    def test_confirm_action_once(self, tmp_path):
        pm = PermissionManager(confirm_callback=lambda _: True)
        assert pm.confirm_action("write", tmp_path / "x.txt") is True

    def test_confirm_action_deny(self, tmp_path):
        pm = PermissionManager(confirm_callback=lambda _: False)
        assert pm.confirm_action("write", tmp_path / "x.txt") is False

    def test_confirm_action_invalid_answer(self, tmp_path):
        def maybe(_):
            return "maybe"
        pm = PermissionManager(confirm_callback=maybe)
        assert pm.confirm_action("write", tmp_path / "x.txt") is False

    def test_confirm_action_persistent_loaded(self, tmp_path):
        pm = PermissionManager(confirm_callback=lambda _: False)
        with mock.patch.object(pm, "_load_persistent_confirmations", return_value={"write:*"}):
            assert pm.confirm_action("write", tmp_path / "x.txt") is True


class TestGlobalManager:
    def test_set_and_get_global_permission_manager(self):
        pm = PermissionManager(exec_level="allow")
        set_global_permission_manager(pm)
        assert get_global_permission_manager() is pm


class TestCheckShellSafety:
    def test_check_shell_safety_no_longer_blocks_by_pattern(self):
        # Human confirmation is the only gate; pattern matching no longer blocks.
        assert check_shell_safety("rm -rf /") is None

    def test_check_shell_safety_allows_safe(self):
        assert check_shell_safety("ls -la") is None


class TestCheckPythonSafety:
    def test_check_python_safety_blocks_import_os(self):
        assert check_python_safety("import os") is not None

    def test_check_python_safety_blocks_from_subprocess(self):
        assert check_python_safety("from subprocess import run") is not None

    def test_check_python_safety_blocks_eval(self):
        assert check_python_safety("eval('1+1')") is not None

    def test_check_python_safety_blocks_os_system(self):
        assert check_python_safety("os.system('ls')") is not None

    def test_check_python_safety_syntax_error(self):
        result = check_python_safety("def broken(")
        assert result is not None
        assert "syntax error" in result

    def test_check_python_safety_disallow_install(self):
        result = check_python_safety("pip install pytest", allow_install=False)
        assert result is not None

    def test_check_python_safety_safe_code(self):
        assert check_python_safety("x = 1 + 1") is None
