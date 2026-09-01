"""Tests for TaskScheduler."""
import pytest
import asyncio
from pathlib import Path
from agent.core.scheduler import TaskScheduler, ScheduledTask


@pytest.mark.asyncio
async def test_scheduler_add_and_run(tmp_path: Path):
    storage = tmp_path / "scheduler.json"
    executed_goals = []

    async def mock_executor(goal: str) -> str:
        executed_goals.append(goal)
        return f"Done: {goal}"

    scheduler = TaskScheduler(storage_path=storage, task_executor=mock_executor)
    task = scheduler.add_task(name="Test Task", goal="run audit check", interval_seconds=1)

    assert task.name == "Test Task"
    assert len(scheduler.list_tasks()) == 1
    assert task.is_due() is True

    # Jalankan due tasks
    results = await scheduler.run_due_tasks()
    assert len(results) == 1
    assert results[0]["status"] == "success"
    assert "run audit check" in executed_goals

    # Sekarang tidak lagi due segera
    assert task.is_due() is False

    # Hapus task
    assert scheduler.remove_task(task.id) is True
    assert len(scheduler.list_tasks()) == 0
