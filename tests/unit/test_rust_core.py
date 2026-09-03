import pytest
from agent.tools.rust_core import RustCoreTool
from agent.tools.file_editor import FileEditorTool

@pytest.mark.asyncio
async def test_rust_core_telemetry():
    tool = RustCoreTool()
    result = await tool.run({"operation": "system_telemetry"})
    assert result.success is True
    assert "cpu" in result.data
    assert "memory" in result.data

@pytest.mark.asyncio
async def test_rust_core_fast_scan():
    tool = RustCoreTool()
    result = await tool.run({"operation": "fast_scan", "path": ".", "limit": 10})
    assert result.success is True
    assert "total_files" in result.data

@pytest.mark.asyncio
async def test_file_editor_view():
    tool = FileEditorTool()
    result = await tool.run({"operation": "view", "path": "config.toml", "start_line": 1, "end_line": 3})
    assert result.success is True
    assert "default_model" in result.data
