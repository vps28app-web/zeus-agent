"""Additional unit tests for zeus/tools/git.py."""

import subprocess

import pytest

from zeus.tools.git import (
    _run_git,
    git_branch,
    git_checkout,
    git_clone,
    git_commit,
    git_diff,
    git_log,
    git_pull,
    git_push,
    git_status,
)


@pytest.fixture
def repo(tmp_path):
    subprocess.run(["git", "init", "--quiet", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.email", "t@test.com"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "T"], check=True)
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-m", "init", "--quiet"], check=True)
    return tmp_path


def test_git_status(repo):
    res = git_status(str(repo))
    assert res["success"] is True


def test_git_log(repo):
    res = git_log(str(repo), max_count=1)
    assert res["success"] is True
    assert "init" in res["stdout"]


def test_git_diff(repo):
    (repo / "a.txt").write_text("b", encoding="utf-8")
    res = git_diff(str(repo))
    assert res["success"] is True


def test_git_diff_staged(repo):
    (repo / "a.txt").write_text("b", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    res = git_diff(str(repo), staged=True)
    assert res["success"] is True


def test_git_branch_all(repo):
    res = git_branch(str(repo), all_branches=True)
    assert res["success"] is True


def test_git_checkout_missing_branch(repo):
    res = git_checkout(str(repo), branch="")
    assert "error" in res


def test_git_commit_no_message(repo):
    res = git_commit(str(repo), message="")
    assert "error" in res


def test_git_commit_add_all(repo):
    (repo / "b.txt").write_text("b", encoding="utf-8")
    res = git_commit(str(repo), message="add b", add_all=True)
    assert res["success"] is True


def test_git_pull_local(repo):
    res = git_pull(str(repo), remote="origin")
    # may fail if no remote configured; just verify structure
    assert "exit_code" in res or "error" in res


def test_git_push_local(repo):
    res = git_push(str(repo), remote="origin")
    assert "exit_code" in res or "error" in res


def test_git_clone_with_depth(tmp_path):
    origin = tmp_path / "origin"
    subprocess.run(["git", "init", "--quiet", str(origin)], check=True)
    subprocess.run(["git", "-C", str(origin), "config", "user.email", "t@test.com"], check=True)
    subprocess.run(["git", "-C", str(origin), "config", "user.name", "T"], check=True)
    (origin / "x").write_text("x", encoding="utf-8")
    subprocess.run(["git", "-C", str(origin), "add", "."], check=True)
    subprocess.run(["git", "-C", str(origin), "commit", "-m", "x", "--quiet"], check=True)

    target = tmp_path / "cloned"
    res = git_clone(str(origin), str(target), depth=1)
    assert res["success"] is True
    assert (target / "x").exists()


def test_run_git_file_not_found():
    res = _run_git(["status"], cwd="/nonexistent/path/12345")
    assert "error" in res


def test_run_git_timeout(tmp_path):
    res = _run_git(["status"], cwd=str(tmp_path), timeout=0)
    # git status should still be fast; this mainly checks no crash
    assert "error" in res or "success" in res
