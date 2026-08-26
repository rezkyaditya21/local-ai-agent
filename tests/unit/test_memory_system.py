"""
tests/unit/test_memory_system.py

Unit test untuk MemorySystem.
"""

from __future__ import annotations

import pytest
from pathlib import Path
from agent.memory.memory_system import MemorySystem, MemoryEntry


@pytest.fixture
def memory_system(tmp_path: Path) -> MemorySystem:
    storage_file = tmp_path / "memory.json"
    return MemorySystem(storage_path=storage_file)


def test_working_memory(memory_system: MemorySystem) -> None:
    memory_system.set_working("current_task", "refactor_database")
    assert memory_system.get_working("current_task") == "refactor_database"
    memory_system.clear_working()
    assert memory_system.get_working("current_task") is None


def test_long_term_memory_search(memory_system: MemorySystem) -> None:
    memory_system.add_long_term("rule_1", "Gunakan HSLTailwind untuk UI styling", category="rule")
    memory_system.add_long_term("bug_1", "Fix SSL handshake failure dengan Bing fallback", category="bugfix")

    results = memory_system.search_long_term("SSL handshake")
    assert len(results) >= 1
    assert results[0].key == "bug_1"
