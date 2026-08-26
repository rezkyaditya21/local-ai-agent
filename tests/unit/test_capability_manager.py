"""
tests/unit/test_capability_manager.py

Unit test untuk CapabilityManager.
"""

from __future__ import annotations

import pytest
from agent.core.capabilities import CapabilityManager, CapabilityMap


def test_detect_capabilities() -> None:
    mgr = CapabilityManager()
    cap_map = mgr.detect_capabilities(configured_models=["llama3.2:3b"])

    assert cap_map.python_version != ""
    assert cap_map.is_available("python") is True
    assert "llama3.2:3b" in cap_map.available_models
