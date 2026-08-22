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


def test_read_file_with_limit_offset(tmp_path):
    f = tmp_path / "multi.txt"
    f.write_text("line1\nline2\nline3\n", encoding="utf-8")
    res = read_file(str(f), limit=1, offset=2)
    assert res["lines"] == ["line2"]
    assert res["total_lines"] == 3


def test_write_file_modifies_existing(tmp_path):
    f = tmp_path / "existing.txt"
    f.write_text("old", encoding="utf-8")
    res = write_file(str(f), "new")
    assert res["action"] == "modified"
    assert "diff" in res
    assert res["old_content"] == "old"


def test_replace_file_content_multiple_not_allowed(tmp_path):
    f = tmp_path / "dup.txt"
    f.write_text("abc abc", encoding="utf-8")
    res = replace_file_content(str(f), "abc", "xyz")
    assert "error" in res


def test_replace_file_content_multiple_allowed(tmp_path):
    f = tmp_path / "dup.txt"
    f.write_text("abc abc", encoding="utf-8")
    res = replace_file_content(str(f), "abc", "xyz", allow_multiple=True)
    assert res["status"] == "success"
    assert res["replacements_made"] == 2


def test_move_file_directory(tmp_path):
    src = tmp_path / "dir"
    src.mkdir()
    (src / "file.txt").write_text("x", encoding="utf-8")

    dest = tmp_path / "moved"
    res = move_file(str(src), str(dest))
    assert res["status"] == "success"
    assert (dest / "file.txt").exists()


def test_copy_file_permission_denied(tmp_path):
    src = tmp_path / "a.txt"
    src.write_text("x", encoding="utf-8")

    pm = PermissionManager(project_dir=tmp_path, file_level="read_only")
    set_file_permission_manager(pm)

    res = copy_file(str(src), str(tmp_path / "b.txt"))
    assert "permission_required" in res


def test_delete_file_success(tmp_path):
    f = tmp_path / "del.txt"
    f.write_text("x", encoding="utf-8")
    res = delete_file(str(f))
    assert res["deleted"] is True
    assert not f.exists()


def test_list_directory_error(tmp_path, monkeypatch):
    pm = PermissionManager(project_dir=tmp_path, file_level="read_only")
    set_file_permission_manager(pm)
    monkeypatch.setattr(pm, "can_list_directory", lambda _path: False)
    res = list_directory(str(tmp_path))
    assert "error" in res


def test_grep_search_invalid_regex(tmp_path):
    res = grep_search("[invalid", path=str(tmp_path))
    assert "error" in res


def test_grep_search_with_includes(tmp_path):
    (tmp_path / "a.py").write_text("target", encoding="utf-8")
    (tmp_path / "b.txt").write_text("target", encoding="utf-8")

    res = grep_search("target", path=str(tmp_path), includes=["*.py"])
    assert res["total_matches"] == 1
    assert res["matches"][0]["path"].endswith("a.py")


def test_grep_search_skips_ignored_dirs(tmp_path):
    cache = tmp_path / "__pycache__"
    cache.mkdir()
    (cache / "x.py").write_text("target", encoding="utf-8")

    res = grep_search("target", path=str(tmp_path))
    assert res["total_matches"] == 0


def test_search_files_alias():
    from zeus.tools.file import search_files as sf
    res = sf("target", path=".")
    assert isinstance(res, dict)
