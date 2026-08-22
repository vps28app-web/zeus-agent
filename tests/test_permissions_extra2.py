"""Additional unit tests for zeus/security/permissions.py edge cases."""

from pathlib import Path

from zeus.security.permissions import PermissionManager


def test_is_inside_project_with_symlink_outside(tmp_path):
    outside = tmp_path.parent / "outside_symlink_target"
    outside.mkdir(exist_ok=True)
    link = tmp_path / "link"
    link.symlink_to(outside)

    pm = PermissionManager(project_dir=tmp_path, file_level="project_only")
    assert pm._is_inside_project(link) is False


def test_is_inside_project_path_does_not_exist(tmp_path):
    pm = PermissionManager(project_dir=tmp_path, file_level="project_only")
    inside = tmp_path / "new_file.txt"
    assert pm._is_inside_project(inside) is True


def test_confirm_action_once_then_deny():
    def callback_once(m):
        return True

    def callback_no(m):
        return False

    pm = PermissionManager(file_level="read_only", confirm_callback=callback_once)
    assert pm.confirm_action("write", Path("/tmp/x.txt")) is True

    pm.confirm_callback = callback_no
    assert pm.confirm_action("write", Path("/tmp/y.txt")) is False


def test_grant_permission_persist_loads(tmp_path, monkeypatch):
    monkeypatch.setenv("ZEUS_HOME", str(tmp_path))
    pm = PermissionManager(file_level="read_only", user_id="persist_u")
    pm.grant_permission("write", Path("/tmp/z.txt"), scope="persist")

    pm2 = PermissionManager(file_level="read_only", user_id="persist_u")
    assert pm2.confirm_action("write", Path("/tmp/z.txt")) is True


def test_grant_permission_unknown_scope_defaults_to_once():
    pm = PermissionManager(file_level="read_only")
    pm.grant_permission("write", Path("/tmp/x.txt"), scope="unknown")
    assert pm.confirm_action("write", Path("/tmp/x.txt")) is True


def test_ensure_delete_allowed_allows_when_can_delete(tmp_path):
    f = tmp_path / "del.txt"
    f.write_text("x", encoding="utf-8")
    pm = PermissionManager(project_dir=tmp_path, file_level="project_only")
    pm.ensure_delete_allowed(f)


def test_can_install_packages():
    pm = PermissionManager(exec_level="sandbox_only")
    assert pm.can_install_packages() is True


def test_can_run_terminal_false():
    pm = PermissionManager(exec_level="deny")
    assert pm.can_run_terminal() is False
