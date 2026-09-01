"""Tests for planner replan functionality."""
import pytest
from agent.core.planner import MultiStepPlanner, ExecutionPlan, SubTask


@pytest.fixture
def planner():
    return MultiStepPlanner()


def test_execution_plan_advance():
    plan = ExecutionPlan(goal="write tests")
    plan.subtasks = [
        SubTask(id=1, description="Step 1", action_type="tool_call", status="pending"),
        SubTask(id=2, description="Step 2", action_type="tool_call", status="pending"),
    ]
    plan.current_step = 0
    assert plan.current_subtask == plan.subtasks[0]
    plan.advance()
    assert plan.current_subtask == plan.subtasks[1]
    # advance() won't go past last subtask
    plan.advance()
    assert plan.current_subtask == plan.subtasks[1]


def test_execution_plan_single_task():
    plan = ExecutionPlan(goal="write tests")
    plan.subtasks = [
        SubTask(id=1, description="Step 1", action_type="tool_call", status="pending"),
    ]
    plan.current_step = 0
    assert plan.current_subtask == plan.subtasks[0]
    plan.advance()
    # single task: 0 < 0 is False so step stays at 0
    assert plan.current_subtask == plan.subtasks[0]


def test_execution_plan_empty():
    plan = ExecutionPlan(goal="write tests")
    assert plan.current_subtask is None
    assert len(plan.pending_subtasks) == 0


def test_execution_plan_mark_all_completed():
    plan = ExecutionPlan(goal="write tests")
    plan.subtasks = [
        SubTask(id=1, description="Step 1", action_type="tool_call", status="pending"),
        SubTask(id=2, description="Step 2", action_type="tool_call", status="pending"),
    ]
    plan.current_step = 0
    plan.mark_all_completed()
    assert all(s.status == "completed" for s in plan.subtasks)
    assert plan.completed is True


def test_execution_plan_pending_subtasks():
    plan = ExecutionPlan(goal="write tests")
    plan.subtasks = [
        SubTask(id=1, description="Step 1", action_type="tool_call", status="completed"),
        SubTask(id=2, description="Step 2", action_type="tool_call", status="pending"),
        SubTask(id=3, description="Step 3", action_type="tool_call", status="pending"),
    ]
    assert len(plan.pending_subtasks) == 2
    assert all(s.status == "pending" for s in plan.pending_subtasks)


def test_execution_plan_completed_count():
    plan = ExecutionPlan(goal="write tests")
    plan.subtasks = [
        SubTask(id=1, description="Step 1", action_type="tool_call", status="completed"),
        SubTask(id=2, description="Step 2", action_type="tool_call", status="pending"),
    ]
    assert plan.completed_count == 1
    assert plan.failed_count == 0


def test_execution_plan_failed_count():
    plan = ExecutionPlan(goal="write tests")
    plan.subtasks = [
        SubTask(id=1, description="Step 1", action_type="tool_call", status="failed"),
        SubTask(id=2, description="Step 2", action_type="tool_call", status="completed"),
    ]
    assert plan.failed_count == 1


def test_create_plan_from_tool_calls(planner):
    from agent.models.schemas import ToolCall
    calls = [
        ToolCall(tool_name="shell", params={"command": "ls"}),
        ToolCall(tool_name="filesystem", params={"path": "/tmp"}),
    ]
    plan = planner.create_plan(goal="list files", tool_calls=calls)
    # plan includes tool subtasks + a verification subtask
    assert len(plan.subtasks) >= 2
    assert plan.subtasks[0].description == "Eksekusi tool 'shell'"
    assert plan.subtasks[0].tool_call == calls[0]
