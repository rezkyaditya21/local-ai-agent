"""
tests/unit/test_git_tool.py

Unit test untuk GitTool.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from agent.tools.git_tool import GitTool
from agent.models.schemas import ToolResult


@pytest.fixture
def git_tool() -> GitTool:
    return GitTool()


def test_git_tool_schema(git_tool: GitTool) -> None:
    assert git_tool.name == "git"
    assert "status" in git_tool.input_schema["properties"]["operation"]["enum"]


@pytest.mark.asyncio
async def test_git_status_mock(git_tool: GitTool) -> None:
    with patch("shutil.which", return_value="/usr/bin/git"), \
         patch.object(GitTool, "_run_git", new_callable=AsyncMock) as mock_git:
        mock_git.return_value = " M agent/main.py\n"

        result = await git_tool.run({"operation": "status"})
        assert result.success is True
        assert result.data["operation"] == "status"
        assert "main.py" in result.data["output"]
