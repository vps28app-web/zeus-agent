"""Scheduler tools for Zeus: schedule, list, and cancel background tasks."""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from croniter import croniter

from zeus.core.registry import register_tool
from zeus.db.repository import ScheduledTaskRepository
from zeus.scheduler.runner import start_scheduler


def schedule_task(
    command: str,
    schedule: str,
    description: Optional[str] = None,
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Schedule a task to run on a cron schedule.

    Args:
        command: The query/command to execute when the task runs.
        schedule: Cron expression (e.g. '0 9 * * *' = every day at 9am).
        description: Optional human-readable description.
        session_id: Optional session ID to associate with the task.
    """
    # Validate cron expression
    try:
        cron = croniter(schedule, datetime.now(timezone.utc))
        next_run = cron.get_next(datetime)
    except Exception:
        return {"error": f"Invalid cron expression: '{schedule}'"}

    task_id = uuid.uuid4().hex[:12]

    repo = ScheduledTaskRepository()
    repo.create(
        task_id=task_id,
        session_id=session_id or "scheduler",
        command=command,
        schedule=schedule,
        description=description,
        next_run=next_run.isoformat(),
    )

    # Ensure scheduler is running
    start_scheduler()

    return {
        "task_id": task_id,
        "schedule": schedule,
        "next_run": next_run.isoformat(),
        "description": description,
    }


def list_scheduled() -> Dict[str, Any]:
    """List all scheduled tasks."""
    repo = ScheduledTaskRepository()
    tasks = repo.list_all()
    return {
        "tasks": [
            {
                "task_id": t["task_id"],
                "schedule": t["schedule"],
                "next_run": t["next_run"],
                "description": t["description"],
                "enabled": bool(t["enabled"]),
                "created_at": t["created_at"],
            }
            for t in tasks
        ],
        "count": len(tasks),
    }


def cancel_task(task_id: str) -> Dict[str, Any]:
    """Cancel and delete a scheduled task by its ID."""
    repo = ScheduledTaskRepository()
    task = repo.get(task_id)
    if not task:
        return {"error": f"Task not found: {task_id}"}
    repo.delete(task_id)
    return {"task_id": task_id, "deleted": True}


register_tool(
    name="schedule_task",
    description="Schedule a task to run on a cron schedule. The task will execute the given command/query automatically at the specified times.",
    parameters={
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "The query/command to execute."},
            "schedule": {"type": "string", "description": "Cron expression (e.g. '0 9 * * *' = daily at 9am, '*/5 * * * *' = every 5 minutes)."},
            "description": {"type": "string", "description": "Optional description for the task."},
            "session_id": {"type": "string", "description": "Optional session ID to associate."},
        },
        "required": ["command", "schedule"],
    },
    handler=schedule_task,
)

register_tool(
    name="list_scheduled",
    description="List all scheduled tasks with their cron schedules and next run times.",
    parameters={"type": "object", "properties": {}},
    handler=list_scheduled,
)

register_tool(
    name="cancel_task",
    description="Cancel and delete a scheduled task by its task_id.",
    parameters={
        "type": "object",
        "properties": {
            "task_id": {"type": "string", "description": "The ID of the task to cancel."},
        },
        "required": ["task_id"],
    },
    handler=cancel_task,
)
