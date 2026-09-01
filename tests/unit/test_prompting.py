"""Tests for goal-aware prompt building."""
import pytest
from agent.core.prompting import build_task_prompt, build_memory_context, format_memory_entries
from agent.core.evaluator import VerificationResult
from agent.models.schemas import ToolResult


def test_build_task_prompt_basic():
    prompt = build_task_prompt(
        goal="Write unit tests for calculator.py",
        tool_catalog="filesystem: read/write files\nshell: run commands",
        iteration=1,
        budget_summary="Iterasi tersisa: 14 | Tool calls tersisa: 49",
    )
    assert "Write unit tests for calculator.py" in prompt
    assert "filesystem" in prompt
    assert "shell" in prompt
    assert "Iterasi tersisa: 14" in prompt


def test_build_task_prompt_with_memory():
    prompt = build_task_prompt(
        goal="fix tests",
        tool_catalog="test_runner",
        iteration=2,
        budget_summary="13 iterations left",
        memory_text="Project uses pytest",
    )
    assert "Project uses pytest" in prompt


def test_build_task_prompt_with_results():
    results = [ToolResult(success=True, data={"output": "ok"}, tool_name="shell")]
    prompt = build_task_prompt(
        goal="run tests",
        tool_catalog="shell",
        iteration=3,
        budget_summary="12 left",
        last_results=results,
    )
    assert "shell" in prompt
    assert "berhasil" in prompt


def test_build_task_prompt_with_eval():
    eval_result = VerificationResult(
        is_verified=True,
        confidence_score=0.9,
        evidence=["test passed"],
    )
    prompt = build_task_prompt(
        goal="fix tests",
        tool_catalog="test_runner",
        iteration=2,
        budget_summary="13 left",
        last_eval=eval_result,
    )
    assert "sehat" in prompt
    assert "test passed" in prompt


def test_build_memory_context_empty():
    ctx = build_memory_context()
    assert ctx == ""


def test_build_memory_context_with_working():
    ctx = build_memory_context(working={"project_type": "python"})
    assert "python" in ctx
    assert "Working Memory" in ctx


def test_build_memory_context_with_task_history():
    history = [{"goal": "fix tests", "status": "completed"}]
    ctx = build_memory_context(task_history=history)
    assert "fix tests" in ctx
    assert "Riwayat Tugas" in ctx


def test_build_memory_context_with_self_knowledge():
    sk = {"tool_failure_patterns": {"shell": 3}, "successful_strategies": [{"strategy": "use subprocess"}]}
    ctx = build_memory_context(self_knowledge=sk)
    assert "shell" in ctx
    assert "use subprocess" in ctx


def test_format_memory_entries_empty():
    result = format_memory_entries([])
    assert result == ""


def test_format_memory_entries():
    from agent.memory.memory_system import MemoryEntry
    entries = [
        MemoryEntry(key="k1", content="c1", category="fact", created_at=""),
        MemoryEntry(key="k2", content="c2", category="bugfix", created_at=""),
    ]
    result = format_memory_entries(entries)
    assert "k1" in result
    assert "k2" in result
    assert "fact" in result
    assert "bugfix" in result
