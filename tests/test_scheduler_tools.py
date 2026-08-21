"""Unit tests for zeus/tools/scheduler.py."""


import pytest

from zeus.db.connection import init_db
from zeus.tools.scheduler import cancel_task, list_scheduled, schedule_task


@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "test.db"
    init_db(path)
    return path


@pytest.fixture
def patch_db_path(db_path, monkeypatch):
    from zeus.db import connection

    original = connection.get_db_path
    connection.get_db_path = lambda: db_path
    yield
    connection.get_db_path = original


@pytest.fixture(autouse=True)
def stop_scheduler(monkeypatch):
    """Prevent the scheduler thread from starting during tests."""
    monkeypatch.setattr("zeus.tools.scheduler.start_scheduler", lambda: None)


def test_schedule_task_valid_cron(patch_db_path):
    res = schedule_task("echo hello", "0 9 * * *", description="morning greeting")
    assert "task_id" in res
    assert res["schedule"] == "0 9 * * *"
    assert res["description"] == "morning greeting"
    assert "next_run" in res


def test_schedule_task_invalid_cron(patch_db_path):
    res = schedule_task("echo hello", "not a cron")
    assert "error" in res


def test_list_scheduled_tasks(patch_db_path):
    schedule_task("cmd1", "0 9 * * *")
    schedule_task("cmd2", "*/5 * * * *")

    res = list_scheduled()
    assert res["count"] == 2
    assert all("task_id" in t for t in res["tasks"])


def test_cancel_task_existing(patch_db_path):
    created = schedule_task("cmd", "0 9 * * *")
    res = cancel_task(created["task_id"])
    assert res["deleted"] is True


def test_cancel_task_missing(patch_db_path):
    res = cancel_task("nonexistent-id")
    assert "error" in res
