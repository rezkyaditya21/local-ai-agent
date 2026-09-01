"""Tests for GoalStatus and GoalEvaluation schemas."""
import pytest
from agent.models.schemas import GoalStatus, GoalEvaluation


def test_goal_status_values():
    assert GoalStatus.IN_PROGRESS == "in_progress"
    assert GoalStatus.COMPLETED == "completed"
    assert GoalStatus.FAILED == "failed"
    assert GoalStatus.EXHAUSTED == "exhausted"


def test_goal_evaluation_fields():
    eval_result = GoalEvaluation(
        status=GoalStatus.COMPLETED,
        confidence=0.9,
        evidence=["tests passed"],
        failure_reasons=[],
        should_replan=False,
        next_steps=[],
    )
    assert eval_result.status == GoalStatus.COMPLETED
    assert eval_result.confidence == 0.9
    assert eval_result.evidence == ["tests passed"]


def test_goal_evaluation_with_failures():
    eval_result = GoalEvaluation(
        status=GoalStatus.FAILED,
        confidence=0.2,
        evidence=[],
        failure_reasons=["test still failing", "code not compiling"],
        should_replan=True,
        next_steps=["fix tests"],
    )
    assert eval_result.status == GoalStatus.FAILED
    assert len(eval_result.failure_reasons) == 2
    assert eval_result.should_replan is True
