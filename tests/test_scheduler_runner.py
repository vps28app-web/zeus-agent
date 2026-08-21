"""Unit tests for zeus/scheduler/runner.py."""

from datetime import datetime, timezone

import pytest

from zeus.db.connection import get_connection, init_db
from zeus.scheduler import runner as runner_module
from zeus.scheduler.runner import SchedulerRunner, start_scheduler, stop_scheduler


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
def reset_scheduler():
    stop_scheduler()
    yield
    stop_scheduler()


def test_scheduler_start_stop():
    runner = SchedulerRunner(poll_interval=0.01)
    runner.start()
    assert runner._thread is not None
    assert runner._thread.is_alive()
    runner.stop()
    assert runner._thread is None or not runner._thread.is_alive()


def test_start_scheduler_singleton(patch_db_path):
    r1 = start_scheduler(poll_interval=0.01)
    r2 = start_scheduler(poll_interval=0.01)
    assert r1 is r2
    stop_scheduler()


def test_process_due_executes_and_advances(patch_db_path):
    runner = SchedulerRunner(poll_interval=60.0)
    runner._repo.create(
        task_id="t1",
        session_id="s1",
        command="hello",
        schedule="0 9 * * *",
        next_run=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
    )

    executed = {"called": False, "result": None}

    def fake_run_agent(query, session_id=None):
        executed["called"] = True
        executed["result"] = query
        return "done"

    original_run_agent = runner_module.run_agent
    runner_module.run_agent = fake_run_agent
    try:
        runner._process_due()
    finally:
        runner_module.run_agent = original_run_agent

    assert executed["called"] is True
    assert executed["result"] == "hello"

    task = runner._repo.get("t1")
    assert task is not None
    assert task["next_run"] is not None


def test_execute_task_logs_error(patch_db_path):
    runner = SchedulerRunner(poll_interval=60.0)

    def failing_run_agent(query, session_id=None):
        raise RuntimeError("boom")

    original_run_agent = runner_module.run_agent
    runner_module.run_agent = failing_run_agent
    try:
        runner._execute_task({
            "task_id": "t2",
            "command": "fail",
            "session_id": "s2",
            "schedule": "0 9 * * *",
        })
    finally:
        runner_module.run_agent = original_run_agent

    # Error should be logged to metrics table.
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM metrics WHERE session_id = ?", ("t2",)
        ).fetchone()
        assert row is not None
        assert row["error"] == 1
    finally:
        conn.close()
