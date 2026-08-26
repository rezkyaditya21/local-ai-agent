"""
tests/unit/test_code_search.py

Unit test untuk CodeSearchTool.
"""

from __future__ import annotations

import pytest
from pathlib import Path
from agent.tools.code_search import CodeSearchTool
from agent.models.schemas import ToolResult


@pytest.fixture
def code_search_tool() -> CodeSearchTool:
    return CodeSearchTool()


@pytest.mark.asyncio
async def test_search_symbol(code_search_tool: CodeSearchTool, tmp_path: Path) -> None:
    test_file = tmp_path / "sample.py"
    test_file.write_text("class MySampleClass:\n    def sample_method(self):\n        pass\n", encoding="utf-8")

    result = await code_search_tool.run({
        "operation": "search_symbol",
        "query": "MySampleClass",
        "path": str(tmp_path),
    })

    assert result.success is True
    assert len(result.data["matches"]) >= 1
    assert "MySampleClass" in result.data["matches"][0]["content"]


@pytest.mark.asyncio
async def test_find_files(code_search_tool: CodeSearchTool, tmp_path: Path) -> None:
    test_file = tmp_path / "foo.py"
    test_file.write_text("print('hello')", encoding="utf-8")

    result = await code_search_tool.run({
        "operation": "find_files",
        "query": "*.py",
        "path": str(tmp_path),
    })

    assert result.success is True
    assert len(result.data["matches"]) >= 1
    assert result.data["matches"][0]["file"] == "foo.py"
