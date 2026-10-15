"""Additional unit tests for zeus/tools/file.py."""

import pytest

from zeus.security.permissions import PermissionManager
from zeus.tools.file import (
    copy_file,
    delete_file,
    grep_search,
    list_directory,
    move_file,
    read_file,
    replace_file_content,
    set_file_permission_manager,
    write_file,
)


@pytest.fixture(autouse=True)
def setup_permissions(tmp_path):
    pm = PermissionManager(project_dir=tmp_path, file_level="project_only")
    set_file_permission_manager(pm)
    return tmp_path


def test_write_file_creates_parents(tmp_path):
    f = tmp_path / "deep" / "nested" / "file.txt"
    res = write_file(str(f), "data")
    assert res["status"] == "success"
    assert f.exists()


def test_write_file_permission_required(tmp_path, monkeypatch):
    pm = PermissionManager(project_dir=tmp_path, file_level="read_only")
    set_file_permission_manager(pm)

    f = tmp_path / "blocked.txt"
    res = write_file(str(f), "x")
    assert "permission_required" in res


def test_replace_file_content_not_found(tmp_path):
    f = tmp_path / "missing.txt"
    res = replace_file_content(str(f), "old", "new")
    assert "error" in res


def test_replace_file_content_zero_count(tmp_path):
    f = tmp_path / "sample.txt"
    f.write_text("abc", encoding="utf-8")
    res = replace_file_content(str(f), "xyz", "new")
    assert "error" in res


def test_move_file_source_missing(tmp_path):
    res = move_file(str(tmp_path / "a.txt"), str(tmp_path / "b.txt"))
    assert "error" in res


def test_move_file_permission_denied(tmp_path, monkeypatch):
    src = tmp_path / "a.txt"
    src.write_text("x", encoding="utf-8")

    pm = PermissionManager(project_dir=tmp_path, file_level="read_only")
    set_file_permission_manager(pm)

    res = move_file(str(src), str(tmp_path / "b.txt"))
    assert "permission_required" in res


def test_copy_file_source_missing(tmp_path):
    res = copy_file(str(tmp_path / "a.txt"), str(tmp_path / "b.txt"))
    assert "error" in res


def test_copy_file_directory(tmp_path):
    src = tmp_path / "dir"
    src.mkdir()
    (src / "file.txt").write_text("x", encoding="utf-8")

    dest = tmp_path / "dir_copy"
    res = copy_file(str(src), str(dest))
    assert res["status"] == "success"
    assert (dest / "file.txt").exists()


def test_delete_file_not_a_file(tmp_path):
    d = tmp_path / "folder"
    d.mkdir()
    res = delete_file(str(d))
    assert "error" in res


def test_delete_file_permission_denied(tmp_path):
    f = tmp_path / "x.txt"
    f.write_text("x", encoding="utf-8")

    pm = PermissionManager(project_dir=tmp_path, file_level="read_only")
    set_file_permission_manager(pm)

    res = delete_file(str(f))
    assert "permission_required" in res


def test_list_directory_permission_denied(tmp_path, monkeypatch):
    pm = PermissionManager(project_dir=tmp_path, file_level="read_only")
    set_file_permission_manager(pm)
    monkeypatch.setattr(pm, "can_list_directory", lambda _path: False)
    res = list_directory(str(tmp_path))
    assert "error" in res


def test_read_file_permission_denied(tmp_path):
    pm = PermissionManager(project_dir=tmp_path, file_level="deny")
    set_file_permission_manager(pm)
    res = read_file(str(tmp_path / "x.txt"))
    assert "error" in res


def test_project_only_blocks_external_read_listing_and_copy(tmp_path):
    outside = tmp_path.parent / f"{tmp_path.name}_outside.txt"
    destination = tmp_path / "copied.txt"
    outside.write_text("outside secret", encoding="utf-8")
    try:
        assert "error" in read_file(str(outside))
        assert "error" in list_directory(str(tmp_path.parent))
        assert "error" in copy_file(str(outside), str(destination))
        assert not destination.exists()
    finally:
        outside.unlink(missing_ok=True)


def test_project_only_grep_does_not_read_external_symlink(tmp_path):
    outside = tmp_path.parent / f"{tmp_path.name}_external.py"
    link = tmp_path / "external.py"
    outside.write_text("def zeus_external_secret_marker(): pass\n", encoding="utf-8")
    link.symlink_to(outside)
    try:
        result = grep_search("zeus_external_secret_marker", path=str(tmp_path))
        assert result["total_matches"] == 0
    finally:
        outside.unlink(missing_ok=True)
