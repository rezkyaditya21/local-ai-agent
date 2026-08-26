"""Root conftest.py — shared fixtures for all test suites."""

import asyncio
import pytest
from pathlib import Path


# ---------------------------------------------------------------------------
# Event loop
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def event_loop_policy():
    """Use the default asyncio event loop policy for the entire test session."""
    return asyncio.DefaultEventLoopPolicy()


# ---------------------------------------------------------------------------
# Temporary paths
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_agent_dir(tmp_path: Path) -> Path:
    """Return a temporary directory pre-structured for agent tests.

    Layout::

        <tmp>/
            config.toml
            audit.log       (empty, created on demand)
            backups/
            plugins/
    """
    (tmp_path / "backups").mkdir()
    (tmp_path / "plugins").mkdir()
    config = tmp_path / "config.toml"
    config.write_text(
        'default_model = "test"\n'
        "tool_directories = []\n"
        "sandbox_enabled = false\n"
        "shell_timeout_seconds = 30\n"
        'log_path = "audit.log"\n'
        "max_consecutive_actions = 10\n"
        "\n"
        "[model_parameters]\n"
        "temperature = 0.7\n"
        "context_length = 4096\n",
        encoding="utf-8",
    )
    return tmp_path


@pytest.fixture
def tmp_config_path(tmp_agent_dir: Path) -> Path:
    """Return the path to the config.toml inside tmp_agent_dir."""
    return tmp_agent_dir / "config.toml"


@pytest.fixture
def tmp_log_path(tmp_agent_dir: Path) -> Path:
    """Return the path to the audit log inside tmp_agent_dir."""
    return tmp_agent_dir / "audit.log"
