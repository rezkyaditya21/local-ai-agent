"""
tests/unit/test_python_exec.py

Unit test untuk PythonExecTool.
"""

from __future__ import annotations

import pytest
from agent.tools.python_exec import PythonExecTool
from agent.models.schemas import ToolResult


@pytest.fixture
def python_exec_tool() -> PythonExecTool:
    return PythonExecTool()


@pytest.mark.asyncio
async def test_python_exec_success(python_exec_tool: PythonExecTool) -> None:
    result = await python_exec_tool.run({"code": "print(2 + 3)"})
    assert result.success is True
    assert result.data["stdout"].strip() == "5"
    assert result.data["exit_code"] == 0


@pytest.mark.asyncio
async def test_python_exec_empty_code(python_exec_tool: PythonExecTool) -> None:
    result = await python_exec_tool.run({"code": "  "})
    assert result.success is False
    assert "tidak boleh kosong" in result.error
