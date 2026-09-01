"""Quick verification tests for orchestrator helper functions."""
import pytest
from agent.core.orchestrator import _utc_now_iso, MAX_CONSECUTIVE_ACTIONS
from agent.core.controller import _parse_tool_calls


def test_utc_now_iso_format():
    ts = _utc_now_iso()
    assert ts.endswith("Z"), f"Should end with Z, got: {ts}"
    assert "T" in ts, f"Should contain T separator, got: {ts}"
    # Should be ISO 8601: 2024-01-01T00:00:00.000Z
    assert len(ts) == 24, f"Expected 24 chars, got {len(ts)}: {ts}"


def test_max_consecutive_actions():
    assert MAX_CONSECUTIVE_ACTIONS == 10


def test_parse_tool_calls_valid():
    text = 'Analyzing... {"tool": "filesystem", "params": {"path": "/tmp/test.txt"}} done.'
    calls = _parse_tool_calls(text)
    assert len(calls) == 1
    assert calls[0].tool_name == "filesystem"
    assert calls[0].params == {"path": "/tmp/test.txt"}


def test_parse_tool_calls_tool_name_variant():
    text = '{"tool_name": "shell", "params": {"command": "ls"}}'
    calls = _parse_tool_calls(text)
    assert len(calls) == 1
    assert calls[0].tool_name == "shell"
    assert calls[0].params == {"command": "ls"}


def test_parse_tool_calls_no_calls():
    calls = _parse_tool_calls("No tool calls here, just plain text.")
    assert calls == []


def test_parse_tool_calls_empty_string():
    calls = _parse_tool_calls("")
    assert calls == []


def test_parse_tool_calls_empty_params():
    text = '{"tool": "noop", "params": {}}'
    calls = _parse_tool_calls(text)
    assert len(calls) == 1
    assert calls[0].tool_name == "noop"
    assert calls[0].params == {}


def test_parse_tool_calls_no_tool_name_key():
    # JSON object without "tool" or "tool_name" key should be ignored
    text = '{"action": "something", "params": {}}'
    calls = _parse_tool_calls(text)
    assert calls == []


def test_parse_tool_calls_multiple():
    text = (
        '{"tool": "filesystem", "params": {"path": "/a"}} '
        'then {"tool": "shell", "params": {"command": "pwd"}}'
    )
    calls = _parse_tool_calls(text)
    assert len(calls) == 2
    assert calls[0].tool_name == "filesystem"
    assert calls[1].tool_name == "shell"


@pytest.mark.asyncio
async def test_agent_process_executes_tool():
    from unittest.mock import AsyncMock, MagicMock
    from agent.core.orchestrator import Agent
    from agent.core.executor import Executor
    from agent.core.confirmation_gate import ConfirmationGate
    from agent.core.audit_logger import AuditLogger
    from agent.core.blocklist import Blocklist
    from agent.tools.registry import ToolRegistry
    from agent.tools.shell import ShellTool

    # Setup mocks
    mock_mm = MagicMock()
    # Turn 1 returns a tool call, Turn 2 returns the final explanation
    async def mock_generate(prompt, history=[], **kwargs):
        if "Hasil eksekusi tool" not in prompt:
            yield '{"tool": "shell", "params": {"command": "echo test_output"}}'
        else:
            yield 'Perintah terminal berhasil dijalankan.'

    mock_mm.generate = mock_generate

    registry = ToolRegistry()
    registry.register(ShellTool(), source="builtin")
    gate = ConfirmationGate()
    blocklist = Blocklist()
    audit = MagicMock()

    executor = Executor(registry=registry, confirmation_gate=gate, blocklist=blocklist, audit_logger=audit)
    agent = Agent(model_manager=mock_mm, executor=executor, confirmation_gate=gate, audit_logger=audit, blocklist=blocklist)

    tokens = []
    async for tok in agent.process("jalankan echo test_output"):
        tokens.append(tok)

    output = "".join(tokens)
    assert "Menjalankan tool 'shell'" in output
    assert "Perintah terminal berhasil dijalankan" in output
    assert len(agent.get_history()) == 1
    assert len(agent.get_history()[0].tool_calls) == 1

