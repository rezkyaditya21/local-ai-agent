"""Tests for controller JSON parsing and tool call extraction."""
import pytest
from agent.core.controller import _extract_json_objects, _parse_tool_calls


def test_extract_json_objects_single():
    text = 'Here is the JSON: {"tool": "shell", "params": {"command": "ls"}}'
    results = _extract_json_objects(text)
    assert len(results) == 1
    assert '"tool": "shell"' in results[0]


def test_extract_json_objects_multiple():
    text = '{"tool": "a"} and {"tool": "b"}'
    results = _extract_json_objects(text)
    assert len(results) == 2


def test_extract_json_objects_none():
    text = "No JSON here, just plain text."
    results = _extract_json_objects(text)
    assert results == []


def test_parse_tool_calls_valid():
    text = '{"tool": "shell", "params": {"command": "ls"}}'
    calls = _parse_tool_calls(text)
    assert len(calls) == 1
    assert calls[0].tool_name == "shell"
    assert calls[0].params == {"command": "ls"}


def test_parse_tool_calls_tool_name_variant():
    text = '{"tool_name": "shell", "params": {"command": "pwd"}}'
    calls = _parse_tool_calls(text)
    assert len(calls) == 1
    assert calls[0].tool_name == "shell"


def test_parse_tool_calls_uses_aliases():
    text = '{"tool": "filesystemtool", "params": {"path": "/a"}}'
    calls = _parse_tool_calls(text)
    assert len(calls) == 1
    assert calls[0].tool_name == "filesystem"


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


def test_parse_tool_calls_malformed_json():
    text = '{not valid json}'
    calls = _parse_tool_calls(text)
    assert calls == []
