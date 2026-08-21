"""Unit tests for zeus/tools/git.py."""

import subprocess

from zeus.tools.git import (
    git_branch,
    git_clone,
    git_commit,
    git_log,
    git_status,
)


def _init_repo(path):
    subprocess.run(["git", "init", "--quiet", str(path)], check=True)
    subprocess.run(
        ["git", "-C", str(path), "config", "user.email", "test@test.com"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(path), "config", "user.name", "Test User"],
        check=True,
    )


def test_git_status_clean_repo(tmp_path):
    _init_repo(tmp_path)
    res = git_status(str(tmp_path))
    assert res["success"] is True
    assert res["exit_code"] == 0


def test_git_log_shows_commit(tmp_path):
    _init_repo(tmp_path)
    (tmp_path / "file.txt").write_text("content", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "commit", "-m", "initial", "--quiet"],
        check=True,
    )

    res = git_log(str(tmp_path), max_count=1, oneline=True)
    assert res["success"] is True
    assert "initial" in res["stdout"]


def test_git_branch_current(tmp_path):
    _init_repo(tmp_path)
    res = git_branch(str(tmp_path), all_branches=False)
    assert res["success"] is True
    assert res["stdout"].strip() in ("main", "master")


def test_git_commit_stages_and_commits(tmp_path):
    _init_repo(tmp_path)
    (tmp_path / "a.txt").write_text("hello", encoding="utf-8")

    res = git_commit(str(tmp_path), message="add a.txt", add_all=True)
    assert res["success"] is True

    log = git_log(str(tmp_path), max_count=1, oneline=True)
    assert "add a.txt" in log["stdout"]


def test_git_clone_local_repo(tmp_path):
    origin = tmp_path / "origin"
    _init_repo(origin)
    (origin / "data.txt").write_text("x", encoding="utf-8")
    subprocess.run(["git", "-C", str(origin), "add", "."], check=True)
    subprocess.run(
        ["git", "-C", str(origin), "commit", "-m", "origin commit", "--quiet"],
        check=True,
    )

    target = tmp_path / "cloned"
    res = git_clone(str(origin), str(target))
    assert res["success"] is True
    assert (target / "data.txt").exists()
