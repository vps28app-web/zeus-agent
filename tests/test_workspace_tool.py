from pathlib import Path

from zeus.core.registry import REGISTRY
from zeus.security.permissions import PermissionManager


def _change_workspace_tool():
    tool = REGISTRY.get("change_working_directory")
    assert tool is not None
    return tool.handler


def test_change_workspace_updates_cwd_and_permission_roots(tmp_path, monkeypatch):
    import os

    import zeus.security.permissions as permissions
    import zeus.tools.code_intel as code_intel
    import zeus.tools.file as file_tools

    initial = tmp_path / "initial"
    target = tmp_path / "project"
    initial.mkdir()
    target.mkdir()
    monkeypatch.chdir(initial)
    monkeypatch.setenv("ZEUS_LOCAL_CLI", "1")

    file_pm = PermissionManager(project_dir=initial, file_level="project_only")
    code_pm = PermissionManager(project_dir=initial, file_level="project_only")
    global_pm = PermissionManager(project_dir=initial, file_level="project_only")
    monkeypatch.setattr(file_tools, "_permissions", file_pm)
    monkeypatch.setattr(code_intel, "_permissions", code_pm)
    monkeypatch.setattr(permissions, "_global_permission_manager", global_pm)

    result = _change_workspace_tool()(str(target))

    assert result["status"] == "success"
    assert result["working_directory"] == str(target.resolve())
    assert Path.cwd() == target.resolve()
    assert file_pm.project_dir == target.resolve()
    assert code_pm.project_dir == target.resolve()
    assert global_pm.project_dir == target.resolve()
    assert file_pm.can_read_file(target / "inside.txt")
    assert not file_pm.can_read_file(initial / "outside.txt")
    assert os.environ["ZEUS_PROJECT_DIR"] == str(target.resolve())


def test_change_workspace_rejects_missing_directory_without_switching(tmp_path, monkeypatch):
    initial = tmp_path / "initial"
    initial.mkdir()
    monkeypatch.chdir(initial)
    monkeypatch.setenv("ZEUS_LOCAL_CLI", "1")

    result = _change_workspace_tool()(str(tmp_path / "missing"))

    assert "error" in result
    assert Path.cwd() == initial.resolve()


def test_change_workspace_is_disabled_outside_local_cli(tmp_path, monkeypatch):
    monkeypatch.delenv("ZEUS_LOCAL_CLI", raising=False)
    original = Path.cwd()
    tool = REGISTRY.get("change_working_directory")

    result = _change_workspace_tool()(str(tmp_path))

    assert tool is not None
    assert "ZEUS_LOCAL_CLI" in tool.required_env
    assert not REGISTRY.is_available(tool.name)
    monkeypatch.setenv("ZEUS_LOCAL_CLI", "1")
    assert REGISTRY.is_available(tool.name)
    assert "error" in result
    assert Path.cwd() == original
