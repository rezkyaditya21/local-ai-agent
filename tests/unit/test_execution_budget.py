"""
tests/unit/test_execution_budget.py

Unit test untuk ExecutionBudget.
"""

from __future__ import annotations

import pytest
from agent.core.budget import ExecutionBudget


def test_budget_initialization() -> None:
    budget = ExecutionBudget(max_iterations=10, max_tool_calls=20)
    assert budget.max_iterations == 10
    assert budget.current_iteration == 0

    is_ex, msg = budget.is_exhausted()
    assert is_ex is False


def test_budget_exhaustion_by_iterations() -> None:
    budget = ExecutionBudget(max_iterations=2)
    budget.consume_iteration()
    budget.consume_iteration()

    is_ex, reason = budget.is_exhausted()
    assert is_ex is True
    assert "iterasi" in reason.lower()
