"""
tests/unit/test_tool_registry.py

Unit tests untuk ToolRegistry, ToolInterface, dan ToolEntry.
Memverifikasi perilaku: register, get, enable, disable, validate_plugin_schema,
select_best, dan batas kapasitas.

Requirements yang diuji: 9.1, 9.5, 9.6, 9.7
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from agent.core.exceptions import (
    AgentCapacityExceededError,
    AgentPluginSchemaError,
    AgentToolNotFoundError,
)
from agent.models.schemas import ToolResult
from agent.tools.registry import (
    MAX_TOOLS,
    ToolEntry,
    ToolInterface,
    ToolRegistry,
)


# ---------------------------------------------------------------------------
# Helpers: dummy tools yang memenuhi ToolInterface
# ---------------------------------------------------------------------------


class _DummyTool:
    """Tool minimal yang memenuhi ToolInterface."""

    def __init__(self, name: str = "dummy", description: str = "A dummy tool") -> None:
        self.name = name
        self.description = description
        self.input_schema: dict = {"type": "object"}
        self.output_schema: dict = {"type": "object"}

    async def run(self, params: dict) -> ToolResult:
        return ToolResult(success=True, data=params, tool_name=self.name)


def _make_tool(name: str = "dummy", description: str = "A dummy tool") -> _DummyTool:
    return _DummyTool(name=name, description=description)


# ---------------------------------------------------------------------------
# Tests: register()
# ---------------------------------------------------------------------------


class TestRegister:
    def test_register_single_tool_succeeds(self):
        registry = ToolRegistry()
        tool = _make_tool("file_tool")
        registry.register(tool)
        assert registry.count == 1

    def test_register_sets_enabled_true_by_default(self):
        registry = ToolRegistry()
        tool = _make_tool("my_tool")
        registry.register(tool)
        entries = registry.list_all()
        assert entries[0].enabled is True

    def test_register_builtin_source_by_default(self):
        registry = ToolRegistry()
        tool = _make_tool("my_tool")
        registry.register(tool)
        assert registry.list_all()[0].source == "builtin"

    def test_register_plugin_source(self):
        registry = ToolRegistry()
        tool = _make_tool("ext_tool")
        registry.register(tool, source="plugin")
        assert registry.list_all()[0].source == "plugin"

    def test_register_updates_existing_tool(self):
        """Pendaftaran ulang dengan nama yang sama menimpa entri lama."""
        registry = ToolRegistry()
        tool_v1 = _make_tool("my_tool", description="v1")
        tool_v2 = _make_tool("my_tool", description="v2")
        registry.register(tool_v1)
        registry.register(tool_v2)  # harus berhasil (bukan error kapasitas)
        assert registry.count == 1
        assert registry.get("my_tool").description == "v2"  # type: ignore[union-attr]

    def test_register_raises_capacity_exceeded_at_200(self):
        """Raise E017 saat registry sudah penuh (200 tool)."""
        registry = ToolRegistry()
        for i in range(MAX_TOOLS):
            registry.register(_make_tool(f"tool_{i}"))

        assert registry.count == MAX_TOOLS

        with pytest.raises(AgentCapacityExceededError) as exc_info:
            registry.register(_make_tool("tool_overflow"))

        err = exc_info.value
        assert err.error_code == "E017"
        assert err.max_capacity == MAX_TOOLS
        assert "tool_overflow" in err.tool_name

    def test_register_raises_plugin_schema_error_missing_name(self):
        """Raise E014 jika tool tidak memiliki field 'name'."""

        class _BadTool:
            description = "bad"
            input_schema: dict = {}
            output_schema: dict = {}

            async def run(self, params: dict) -> ToolResult:
                return ToolResult(success=True, data=None)

        registry = ToolRegistry()
        with pytest.raises(AgentPluginSchemaError) as exc_info:
            registry.register(_BadTool())  # type: ignore[arg-type]

        assert "name" in exc_info.value.missing_fields
        assert exc_info.value.error_code == "E014"

    def test_register_raises_plugin_schema_error_missing_run(self):
        """Raise E014 jika tool tidak memiliki method 'run'."""

        class _NoRunTool:
            name = "no_run"
            description = "no run method"
            input_schema: dict = {}
            output_schema: dict = {}

        registry = ToolRegistry()
        with pytest.raises(AgentPluginSchemaError) as exc_info:
            registry.register(_NoRunTool())  # type: ignore[arg-type]

        assert "run" in exc_info.value.missing_fields

    def test_register_raises_plugin_schema_error_wrong_type(self):
        """Raise E014 jika input_schema bukan dict."""

        class _WrongSchemaTool:
            name = "bad_schema"
            description = "wrong schema type"
            input_schema = "not a dict"   # salah tipe
            output_schema: dict = {}

            async def run(self, params: dict) -> ToolResult:
                return ToolResult(success=True, data=None)

        registry = ToolRegistry()
        with pytest.raises(AgentPluginSchemaError) as exc_info:
            registry.register(_WrongSchemaTool())  # type: ignore[arg-type]

        assert "input_schema" in exc_info.value.missing_fields


# ---------------------------------------------------------------------------
# Tests: get()
# ---------------------------------------------------------------------------


class TestGet:
    def test_get_registered_tool(self):
        registry = ToolRegistry()
        tool = _make_tool("shell")
        registry.register(tool)
        result = registry.get("shell")
        assert result is tool

    def test_get_nonexistent_tool_returns_none(self):
        registry = ToolRegistry()
        assert registry.get("nonexistent") is None

    def test_get_disabled_tool_returns_none(self):
        registry = ToolRegistry()
        tool = _make_tool("db_tool")
        registry.register(tool)
        registry.disable("db_tool")
        assert registry.get("db_tool") is None

    def test_get_reenabled_tool_returns_tool(self):
        registry = ToolRegistry()
        tool = _make_tool("http_tool")
        registry.register(tool)
        registry.disable("http_tool")
        registry.enable("http_tool")
        assert registry.get("http_tool") is tool


# ---------------------------------------------------------------------------
# Tests: list_all()
# ---------------------------------------------------------------------------


class TestListAll:
    def test_list_all_empty(self):
        registry = ToolRegistry()
        assert registry.list_all() == []

    def test_list_all_returns_all_tools(self):
        registry = ToolRegistry()
        for name in ["tool_c", "tool_a", "tool_b"]:
            registry.register(_make_tool(name))
        entries = registry.list_all()
        assert len(entries) == 3

    def test_list_all_sorted_alphabetically(self):
        registry = ToolRegistry()
        for name in ["tool_c", "tool_a", "tool_b"]:
            registry.register(_make_tool(name))
        names = [e.tool.name for e in registry.list_all()]
        assert names == sorted(names)

    def test_list_all_includes_disabled_tools(self):
        registry = ToolRegistry()
        registry.register(_make_tool("active"))
        registry.register(_make_tool("inactive"))
        registry.disable("inactive")
        entries = registry.list_all()
        assert len(entries) == 2
        statuses = {e.tool.name: e.enabled for e in entries}
        assert statuses["active"] is True
        assert statuses["inactive"] is False


# ---------------------------------------------------------------------------
# Tests: enable() and disable()
# ---------------------------------------------------------------------------


class TestEnableDisable:
    def test_enable_existing_tool(self):
        registry = ToolRegistry()
        registry.register(_make_tool("t1"))
        registry.disable("t1")
        registry.enable("t1")
        assert registry.list_all()[0].enabled is True

    def test_disable_existing_tool(self):
        registry = ToolRegistry()
        registry.register(_make_tool("t1"))
        registry.disable("t1")
        assert registry.list_all()[0].enabled is False

    def test_enable_nonexistent_raises_tool_not_found(self):
        registry = ToolRegistry()
        with pytest.raises(AgentToolNotFoundError) as exc_info:
            registry.enable("ghost")
        assert exc_info.value.error_code == "E021"
        assert "ghost" in exc_info.value.tool_name

    def test_disable_nonexistent_raises_tool_not_found(self):
        registry = ToolRegistry()
        with pytest.raises(AgentToolNotFoundError) as exc_info:
            registry.disable("ghost")
        assert exc_info.value.error_code == "E021"
        assert "ghost" in exc_info.value.tool_name

    def test_enable_disable_does_not_affect_other_tools(self):
        """Enable/disable satu tool tidak mengubah status tool lain (Req 9.6)."""
        registry = ToolRegistry()
        registry.register(_make_tool("a"))
        registry.register(_make_tool("b"))
        registry.disable("a")
        assert registry.get("b") is not None  # "b" tetap aktif

    def test_double_disable_stays_disabled(self):
        registry = ToolRegistry()
        registry.register(_make_tool("t"))
        registry.disable("t")
        registry.disable("t")  # idempotent — tidak raise error
        assert registry.list_all()[0].enabled is False

    def test_double_enable_stays_enabled(self):
        registry = ToolRegistry()
        registry.register(_make_tool("t"))
        registry.enable("t")  # idempotent — tidak raise error
        assert registry.list_all()[0].enabled is True


# ---------------------------------------------------------------------------
# Tests: validate_plugin_schema()
# ---------------------------------------------------------------------------


class TestValidatePluginSchema:
    def test_valid_tool_returns_empty_list(self):
        registry = ToolRegistry()
        tool = _make_tool("valid")
        missing = registry.validate_plugin_schema(tool)
        assert missing == []

    def test_missing_all_fields(self):
        registry = ToolRegistry()
        missing = registry.validate_plugin_schema(object())
        assert set(missing) == {"name", "description", "input_schema", "output_schema", "run"}

    def test_missing_single_field(self):
        class _PartialTool:
            name = "partial"
            description = "missing schemas and run"
            # input_schema, output_schema, run are missing

        registry = ToolRegistry()
        missing = registry.validate_plugin_schema(_PartialTool())
        assert "input_schema" in missing
        assert "output_schema" in missing
        assert "run" in missing
        assert "name" not in missing
        assert "description" not in missing

    def test_run_not_callable_flagged(self):
        class _NonCallableRun:
            name = "t"
            description = "d"
            input_schema: dict = {}
            output_schema: dict = {}
            run = "not_callable"  # wrong type

        registry = ToolRegistry()
        missing = registry.validate_plugin_schema(_NonCallableRun())
        assert "run" in missing


# ---------------------------------------------------------------------------
# Tests: select_best()
# ---------------------------------------------------------------------------


class TestSelectBest:
    def test_select_best_empty_registry_returns_none(self):
        registry = ToolRegistry()
        assert registry.select_best("read a file") is None

    def test_select_best_returns_most_relevant_tool(self):
        registry = ToolRegistry()
        registry.register(_make_tool("filesystem", "read write file operations"))
        registry.register(_make_tool("shell", "execute shell commands"))
        registry.register(_make_tool("browser", "fetch web pages html"))

        result = registry.select_best("read a file from disk")
        assert result is not None
        assert result.name == "filesystem"

    def test_select_best_ignores_disabled_tools(self):
        registry = ToolRegistry()
        registry.register(_make_tool("filesystem", "read write file operations"))
        registry.register(_make_tool("shell", "execute shell commands"))
        registry.disable("filesystem")

        result = registry.select_best("read a file")
        # filesystem is disabled; shell should be returned (or None, but not filesystem)
        assert result is None or result.name != "filesystem"

    def test_select_best_case_insensitive(self):
        registry = ToolRegistry()
        registry.register(_make_tool("HTTP_API", "HTTP requests GET POST"))
        result = registry.select_best("http GET request")
        assert result is not None
        assert result.name == "HTTP_API"

    def test_select_best_empty_query_returns_none(self):
        registry = ToolRegistry()
        registry.register(_make_tool("any_tool", "does something"))
        assert registry.select_best("") is None


# ---------------------------------------------------------------------------
# Tests: properties (count, active_count)
# ---------------------------------------------------------------------------


class TestProperties:
    def test_count_reflects_total(self):
        registry = ToolRegistry()
        for i in range(5):
            registry.register(_make_tool(f"t{i}"))
        assert registry.count == 5

    def test_active_count_reflects_enabled(self):
        registry = ToolRegistry()
        for i in range(4):
            registry.register(_make_tool(f"t{i}"))
        registry.disable("t0")
        registry.disable("t1")
        assert registry.active_count == 2

    def test_active_count_zero_when_all_disabled(self):
        registry = ToolRegistry()
        registry.register(_make_tool("only"))
        registry.disable("only")
        assert registry.active_count == 0
