"""
tests/unit/test_planner.py

Unit test untuk MultiStepPlanner.
"""

from __future__ import annotations

import pytest
from agent.core.planner import MultiStepPlanner, SubTask, ExecutionPlan
from agent.models.schemas import ToolCall


@pytest.fixture
def planner() -> MultiStepPlanner:
    return MultiStepPlanner()


def test_create_plan(planner: MultiStepPlanner) -> None:
    calls = [
        ToolCall(tool_name="code_search", params={"query": "ToolRegistry"}),
        ToolCall(tool_name="test_runner", params={"test_path": "tests"}),
    ]
    plan = planner.create_plan("Refactor registry", calls)

    assert plan.goal == "Refactor registry"
    assert len(plan.subtasks) == 3  # 2 tool calls + 1 verification step
    assert plan.subtasks[0].status == "pending"


def test_update_subtask_status(planner: MultiStepPlanner) -> None:
    calls = [ToolCall(tool_name="filesystem", params={"operation": "list_dir", "path": "."})]
    plan = planner.create_plan("List files", calls)

    planner.update_subtask_status(plan, subtask_id=1, status="completed", result_summary="Listed 5 files")
    assert plan.subtasks[0].status == "completed"
