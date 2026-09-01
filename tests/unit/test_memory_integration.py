"""Tests for memory integration with goal context."""
import pytest
from agent.memory.memory_system import MemorySystem


@pytest.fixture
def memory(tmp_path):
    return MemorySystem(storage_path=tmp_path / "memory.json")


def test_build_context_for_goal_empty(memory):
    ctx = memory.build_context_for_goal("fix tests")
    assert isinstance(ctx, dict)
    assert "working" in ctx
    assert "task_history" in ctx
    assert "self_knowledge" in ctx


def test_build_context_for_goal_with_working(memory):
    memory.set_working("project_type", "python")
    ctx = memory.build_context_for_goal("write tests")
    assert ctx["working"]["project_type"] == "python"


def test_record_tool_failure(memory):
    memory.record_tool_failure("shell", "command timeout")
    failures = memory.get_self_knowledge("tool_failure_patterns", {})
    assert failures.get("shell", 0) == 1


def test_record_successful_strategy(memory):
    memory.record_successful_strategy("shell", "use subprocess.run for long commands")
    strategies = memory.get_self_knowledge("successful_strategies", [])
    assert len(strategies) >= 1


def test_get_task_history(memory):
    memory.add_task_step("write tests", 1, "run pytest", "passed", "completed")
    history = memory.get_task_history(limit=5)
    assert len(history) >= 1


def test_store_task_result_success(memory):
    memory.store_task_result("write tests", "run all tests", success=True)
    strategies = memory.get_self_knowledge("successful_strategies", [])
    assert len(strategies) >= 1


def test_store_task_result_failure(memory):
    memory.store_task_result("fix bug", "apply patch", success=False)
    experiences = memory.get_self_knowledge("debugging_experiences", [])
    assert len(experiences) >= 1


def test_search_long_term(memory):
    memory.add_long_term("python", "Project uses Python 3.11", "fact")
    results = memory.search_long_term("python", limit=5)
    assert len(results) >= 1
    assert results[0].key == "python"


def test_working_memory_roundtrip(memory):
    memory.set_working("key", "value")
    assert memory.get_working("key") == "value"
    memory.clear_working()
    assert memory.get_working("key") is None
