"""Tests for goal-aware ObjectiveEvaluator."""
import pytest
from agent.core.evaluator import ObjectiveEvaluator
from agent.models.schemas import GoalStatus, ToolResult


@pytest.fixture
def evaluator():
    return ObjectiveEvaluator(model_manager=None)


def test_evaluate_tool_results_empty(evaluator):
    result = evaluator.evaluate_tool_results([])
    assert result.is_verified is False
    assert result.confidence_score == 0.0


def test_evaluate_tool_results_all_success(evaluator):
    results = [
        ToolResult(success=True, data={"output": "ok"}, tool_name="shell"),
        ToolResult(success=True, data={"output": "ok"}, tool_name="filesystem"),
    ]
    result = evaluator.evaluate_tool_results(results)
    assert result.is_verified is True
    assert result.confidence_score > 0.5


def test_evaluate_tool_results_with_failure(evaluator):
    results = [
        ToolResult(success=True, data={}, tool_name="shell"),
        ToolResult(success=False, data={}, error="timeout", tool_name="shell"),
    ]
    result = evaluator.evaluate_tool_results(results)
    assert result.is_verified is False
    assert len(result.failure_reasons) > 0


def test_evaluate_tool_results_high_exit_code(evaluator):
    results = [
        ToolResult(success=True, data={"exit_code": 1}, tool_name="shell"),
    ]
    result = evaluator.evaluate_tool_results(results)
    assert result.is_verified is False


@pytest.mark.asyncio
async def test_evaluate_goal_with_test_success(evaluator):
    results = [
        ToolResult(
            success=True,
            data={"failed": 0, "passed": 5},
            tool_name="test_runner",
        ),
    ]
    goal_eval = await evaluator.evaluate_goal(
        goal="run tests",
        results=results,
        iteration=2,
    )
    assert goal_eval.status == GoalStatus.COMPLETED


@pytest.mark.asyncio
async def test_evaluate_goal_with_test_failure(evaluator):
    results = [
        ToolResult(
            success=True,
            data={"failed": 2, "passed": 3},
            tool_name="test_runner",
        ),
    ]
    goal_eval = await evaluator.evaluate_goal(
        goal="fix tests",
        results=results,
        iteration=3,
    )
    assert goal_eval.status != GoalStatus.COMPLETED


@pytest.mark.asyncio
async def test_evaluate_goal_empty_results(evaluator):
    goal_eval = await evaluator.evaluate_goal(
        goal="write tests for calculator",
        results=[],
        iteration=1,
    )
    assert goal_eval.status in (GoalStatus.IN_PROGRESS, GoalStatus.FAILED)


def test_verify_python_syntax_valid(evaluator, tmp_path):
    test_file = tmp_path / "valid.py"
    test_file.write_text("def foo(): return 42\n", encoding="utf-8")
    result = evaluator.verify_python_syntax(test_file)
    assert result.is_verified is True


def test_verify_python_syntax_invalid(evaluator, tmp_path):
    test_file = tmp_path / "invalid.py"
    test_file.write_text("def foo(\n", encoding="utf-8")
    result = evaluator.verify_python_syntax(test_file)
    assert result.is_verified is False
    assert len(result.failure_reasons) > 0
