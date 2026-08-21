"""Unit tests for enhanced file tools in zeus/tools/file.py."""

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
    search_files,
    set_file_permission_manager,
    write_file,
)


@pytest.fixture(autouse=True)
def setup_permissions(tmp_path):
    pm = PermissionManager(project_dir=tmp_path, file_level="project_only")
    set_file_permission_manager(pm)
    return tmp_path


def test_replace_file_content_success(tmp_path):
    f = tmp_path / "sample.txt"
    f.write_text("Hello World\nLine 2\nHello Again\n", encoding="utf-8")

    res = replace_file_content(
        path=str(f),
        target_content="Hello World",
        replacement_content="Hello Zeus",
        allow_multiple=False,
    )

    assert res["status"] == "success"
    assert res["action"] == "modified"
    assert "diff" in res
    assert "🔴 - Hello World" in res["diff"] or "-Hello World" in res["diff"]
    assert f.read_text(encoding="utf-8").startswith("Hello Zeus")


def test_replace_file_content_multiple_requires_flag(tmp_path):
    f = tmp_path / "sample.txt"
    f.write_text("foo bar foo baz", encoding="utf-8")

    res_err = replace_file_content(
        path=str(f),
        target_content="foo",
        replacement_content="qux",
        allow_multiple=False,
    )
    assert "error" in res_err
    assert "Target content found 2 times" in res_err["error"]

    res_ok = replace_file_content(
        path=str(f),
        target_content="foo",
        replacement_content="qux",
        allow_multiple=True,
    )
    assert res_ok["status"] == "success"
    assert f.read_text(encoding="utf-8") == "qux bar qux baz"


def test_move_file(tmp_path):
    src = tmp_path / "old.txt"
    dest = tmp_path / "sub" / "new.txt"
    src.write_text("content to move", encoding="utf-8")

    res = move_file(str(src), str(dest))
    assert res["status"] == "success"
    assert res["action"] == "moved"
    assert not src.exists()
    assert dest.exists()
    assert dest.read_text(encoding="utf-8") == "content to move"


def test_copy_file(tmp_path):
    src = tmp_path / "source.txt"
    dest = tmp_path / "copy.txt"
    src.write_text("original content", encoding="utf-8")

    res = copy_file(str(src), str(dest))
    assert res["status"] == "success"
    assert res["action"] == "copied"
    assert src.exists()
    assert dest.exists()
    assert dest.read_text(encoding="utf-8") == "original content"


def test_grep_search(tmp_path):
    f1 = tmp_path / "app.py"
    f2 = tmp_path / "util.py"
    f3 = tmp_path / "ignore.log"

    f1.write_text("def process_poker_game():\n    pass\n", encoding="utf-8")
    f2.write_text("# poker helper function\ndef calculate_pot():\n    return 100\n", encoding="utf-8")
    f3.write_text("poker debug line\n", encoding="utf-8")

    res = grep_search(
        query="poker",
        path=str(tmp_path),
        includes=["*.py"],
    )

    assert res["status"] == "success"
    assert len(res["matches"]) == 2
    paths = [m["path"] for m in res["matches"]]
    assert str(f1) in paths
    assert str(f2) in paths
    assert str(f3) not in paths


def test_read_file_basic(tmp_path):
    f = tmp_path / "hello.txt"
    f.write_text("line1\nline2\nline3\n", encoding="utf-8")

    res = read_file(str(f), limit=2, offset=1)
    assert res["status"] == "success"
    assert res["lines"] == ["line1", "line2"]
    assert res["total_lines"] == 3


def test_write_file_and_read_back(tmp_path):
    f = tmp_path / "out.txt"

    res = write_file(str(f), "hello world")
    assert res["status"] == "success"
    assert res["action"] == "created"
    assert f.read_text(encoding="utf-8") == "hello world"

    res2 = write_file(str(f), "hello zeus")
    assert res2["action"] == "modified"
    assert "diff" in res2
    assert "old_content" in res2


def test_list_directory(tmp_path):
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    (tmp_path / "sub").mkdir()

    res = list_directory(str(tmp_path))
    names = {e["name"] for e in res["entries"]}
    assert "a.txt" in names
    assert "sub" in names


def test_delete_file(tmp_path):
    f = tmp_path / "delete_me.txt"
    f.write_text("x", encoding="utf-8")

    res = delete_file(str(f))
    assert res["status"] == "success"
    assert not f.exists()


def test_search_files(tmp_path):
    (tmp_path / "a.py").write_text("def foo(): pass\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("def bar(): pass\n", encoding="utf-8")

    res = search_files("def .*\\(\\):", str(tmp_path))
    assert res["status"] == "success"
    assert res["total_matches"] == 2


def test_permission_required_blocks_write_outside_project(tmp_path):
    outside = tmp_path.parent / "outside.txt"

    res = write_file(str(outside), "x")
    assert "permission_required" in res
    assert not outside.exists()
