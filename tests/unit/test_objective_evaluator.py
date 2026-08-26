"""
tests/unit/test_objective_evaluator.py

Unit test untuk ObjectiveEvaluator.
"""

from __future__ import annotations

import pytest
from pathlib import Path
from agent.core.evaluator import ObjectiveEvaluator
from agent.models.schemas import ToolResult


@pytest.fixture
def evaluator() -> ObjectiveEvaluator:
    return ObjectiveEvaluator()


def test_evaluate_tool_results_success(evaluator: ObjectiveEvaluator) -> None:
    results = [
        ToolResult(success=True, data={"exit_code": 0}, tool_name="shell"),
        ToolResult(success=True, data={"passed": 5, "failed": 0}, tool_name="test_runner"),
    ]
    res = evaluator.evaluate_tool_results(results)
    assert res.is_verified is True
    assert res.confidence_score == 1.0


def test_evaluate_tool_results_failure(evaluator: ObjectiveEvaluator) -> None:
    results = [
        ToolResult(success=True, data={"passed": 2, "failed": 1}, tool_name="test_runner"),
    ]
    res = evaluator.evaluate_tool_results(results)
    assert res.is_verified is False
    assert len(res.failure_reasons) >= 1


def test_verify_python_syntax(evaluator: ObjectiveEvaluator, tmp_path: Path) -> None:
    valid_file = tmp_path / "valid.py"
    valid_file.write_text("def hello(): return 42\n", encoding="utf-8")

    res = evaluator.verify_python_syntax(valid_file)
    assert res.is_verified is True

    invalid_file = tmp_path / "invalid.py"
    invalid_file.write_text("def hello(:\n", encoding="utf-8")

    res_inv = evaluator.verify_python_syntax(invalid_file)
    assert res_inv.is_verified is False
