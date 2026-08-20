"""Background scheduler that polls for due tasks and executes them."""

import threading
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from croniter import croniter

from zeus.db.repository import ScheduledTaskRepository

# Singleton runner instance
_scheduler: Optional["SchedulerRunner"] = None
_scheduler_lock = threading.Lock()


class SchedulerRunner:
    """Polls the database for due tasks and executes them in a background thread."""

    def __init__(self, poll_interval: float = 60.0):
        self.poll_interval = poll_interval
        self._repo = ScheduledTaskRepository()
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="zeus-scheduler")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None

    def _run(self) -> None:
        while not self._stop.wait(self.poll_interval):
            self._process_due()

    def _process_due(self) -> None:
        tasks = self._repo.list_due()
        for task in tasks:
            self._execute_task(task)
            self._advance_next_run(task)

    def _execute_task(self, task: Dict[str, Any]) -> None:
        task_id = task["task_id"]
        command = task["command"]
        session_id = task["session_id"]

        print(f"[scheduler] executing task {task_id}: {command[:80]}")

        try:
            result = run_agent(command, session_id=session_id)
            print(f"[scheduler] task {task_id} completed")
            self._log_result(task_id, result, error=False)
        except Exception as e:
            print(f"[scheduler] task {task_id} failed: {e}")
            self._log_result(task_id, str(e), error=True)

    def _log_result(
        self, task_id: str, result: Any, error: bool
    ) -> None:
        from zeus.db.connection import get_connection
        conn = get_connection()
        try:
            conn.execute(
                """INSERT INTO metrics (session_id, tool_name, error, result_summary)
                VALUES (?, ?, ?, ?)""",
                (task_id, "scheduled_task", int(error), str(result)[:500]),
            )
            conn.commit()
        finally:
            conn.close()

    def _advance_next_run(self, task: Dict[str, Any]) -> None:
        schedule = task["schedule"]
        cron = croniter(schedule, datetime.now(timezone.utc))
        next_run = cron.get_next(datetime).isoformat()
        self._repo.update_next_run(task["task_id"], next_run)


def run_agent(query: str, session_id: str) -> str:
    """Run a single agent query and return the response."""
    from zeus.core.agent import run_agent as _run_agent
    return _run_agent(query, session_id=session_id)


def start_scheduler(poll_interval: float = 60.0) -> SchedulerRunner:
    global _scheduler
    with _scheduler_lock:
        if _scheduler is None:
            _scheduler = SchedulerRunner(poll_interval=poll_interval)
            _scheduler.start()
        return _scheduler


def stop_scheduler() -> None:
    global _scheduler
    with _scheduler_lock:
        if _scheduler:
            _scheduler.stop()
            _scheduler = None
