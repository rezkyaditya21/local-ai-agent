"""
tests/unit/test_tool_creator.py

Unit test untuk ToolCreator.
"""

from __future__ import annotations

import pytest
from pathlib import Path
from agent.tools.registry import ToolRegistry
from agent.tools.tool_creator import ToolCreator


@pytest.mark.asyncio
async def test_tool_creator_success(tmp_path: Path) -> None:
    registry = ToolRegistry()
    creator = ToolCreator(registry=registry, target_dir=tmp_path)

    sample_code = '''
from agent.models.schemas import ToolResult

class DynamicMathTool:
    name = "dynamic_math"
    description = "Melakukan penjumlahan matematika"
    input_schema = {"type": "object"}
    output_schema = {"type": "object"}

    async def run(self, params: dict) -> ToolResult:
        return ToolResult(success=True, data={"result": 10}, tool_name=self.name)
'''

    result = await creator.create_and_register_tool(
        tool_name="dynamic_math",
        code_content=sample_code,
    )

    assert result.success is True
    assert registry.get("dynamic_math") is not None
