"""Tests for ExecutionBudget with config-driven setup."""
import pytest
from agent.core.budget import ExecutionBudget


def test_budget_from_config():
    config = {"execution_budget": {"max_iterations": 5, "max_tool_calls": 10, "max_runtime_seconds": 120}}
    budget = ExecutionBudget.from_config(config)
    assert budget.max_iterations == 5
    assert budget.max_tool_calls == 10
    assert budget.max_runtime_seconds == 120


def test_budget_from_config_defaults():
    budget = ExecutionBudget.from_config({})
    assert budget.max_iterations == 15
    assert budget.max_tool_calls == 50
    assert budget.max_runtime_seconds == 300.0


def test_budget_consume_iteration():
    budget = ExecutionBudget(max_iterations=5)
    assert budget.is_exhausted() == (False, "Budget masih tersedia")
    budget.consume_iteration()
    assert budget.current_iteration == 1
    budget.consume_iteration()
    budget.consume_iteration()
    budget.consume_iteration()
    budget.consume_iteration()
    exhausted, reason = budget.is_exhausted()
    assert exhausted is True
    assert "iterasi" in reason.lower()


def test_budget_consume_tool_calls():
    budget = ExecutionBudget(max_tool_calls=3)
    budget.consume_tool_call()
    budget.consume_tool_call()
    assert budget.is_exhausted() == (False, "Budget masih tersedia")
    budget.consume_tool_call()
    exhausted, _ = budget.is_exhausted()
    assert exhausted is True


def test_budget_remaining_summary():
    budget = ExecutionBudget(max_iterations=5, max_tool_calls=10)
    budget.consume_iteration()
    budget.consume_tool_call()
    budget.consume_tool_call()
    summary = budget.remaining_summary()
    assert "4" in summary  # 4 iterations remaining
    assert "8" in summary  # 8 tool calls remaining


def test_budget_increment_retry():
    budget = ExecutionBudget(max_retries=2)
    budget.increment_retry()
    assert budget.retry_count == 1
    budget.increment_retry()
    assert budget.retry_count == 2
    exhausted, reason = budget.is_exhausted()
    assert exhausted is True
    assert "retries" in reason.lower()


def test_budget_consume_tokens():
    budget = ExecutionBudget(max_tokens=100)
    budget.consume_tokens(50)
    assert budget.consumed_tokens == 50
    assert budget.is_exhausted() == (False, "Budget masih tersedia")
    budget.consume_tokens(50)
    exhausted, _ = budget.is_exhausted()
    assert exhausted is True


def test_budget_reset_retry():
    budget = ExecutionBudget(max_retries=3)
    budget.increment_retry()
    budget.increment_retry()
    budget.reset_retry()
    assert budget.retry_count == 0
    assert budget.is_exhausted() == (False, "Budget masih tersedia")


def test_budget_zero_max_retries():
    budget = ExecutionBudget(max_retries=0)
    assert budget.is_exhausted() == (False, "Budget masih tersedia")
    budget.increment_retry()
    exhausted, reason = budget.is_exhausted()
    assert exhausted is True
    assert "retries" in reason.lower()

