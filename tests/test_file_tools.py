"""Unit tests for enhanced file tools in zeus/tools/file.py."""

import pytest
from pathlib import Path
from zeus.tools.file import (
    replace_file_content,
    move_file,
    copy_file,
    grep_search,
    write_file,
    read_file,
    set_file_permission_manager,
)
from zeus.security.permissions import PermissionManager


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
