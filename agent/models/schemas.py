"""
agent/models/schemas.py

Core data models (dataclasses) shared across all agent subsystems.
All fields carry accurate type hints as specified in the design document.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# File System
# ---------------------------------------------------------------------------


@dataclass
class FileEntry:
    """Represents a single filesystem entry (file or directory)."""

    path: str
    name: str
    size_bytes: int
    modified_at: str  # ISO 8601
    entry_type: str   # "file" | "directory"


# ---------------------------------------------------------------------------
# Shell
# ---------------------------------------------------------------------------


@dataclass
class ShellResult:
    """Result of a shell command execution."""

    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False
    command: str = ""


@dataclass
class BackgroundProcess:
    """A process launched in the background."""

    pid: int
    command: str
    status: str          # "running" | "stopped" | "error"
    exit_code: int | None = None


# ---------------------------------------------------------------------------
# Browser
# ---------------------------------------------------------------------------


@dataclass
class ExtractedContent:
    """Structured content extracted from an HTML page."""

    text: str
    links: list[str]
    structured_data: list[dict]  # schema.org / JSON-LD items, etc.


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------


@dataclass
class ColumnInfo:
    """Metadata about a single database column."""

    name: str
    data_type: str
    is_primary_key: bool
    is_nullable: bool
    is_unique: bool


@dataclass
class TableSchema:
    """Schema of a single database table."""

    name: str
    columns: list[ColumnInfo]


@dataclass
class DatabaseSchema:
    """Full schema of a connected database."""

    tables: list[TableSchema]


# ---------------------------------------------------------------------------
# HTTP API
# ---------------------------------------------------------------------------


@dataclass
class HTTPResponse:
    """Response returned by the HTTP API Tool."""

    status_code: int
    headers: dict[str, str]
    body: bytes
    final_url: str        # URL after all redirects
    redirect_count: int


# ---------------------------------------------------------------------------
# Config / Credentials
# ---------------------------------------------------------------------------


@dataclass
class CredentialEntry:
    """An encrypted credential stored in the vault."""

    key: str
    encrypted_value: bytes  # Fernet-encrypted; never exposed as plaintext


@dataclass
class AgentConfig:
    """Top-level agent configuration loaded from config.toml."""

    default_model: str
    models: list            # list[ModelConfig] — avoid circular import
    tool_directories: list[str]
    blocklist_path: str | None
    sandbox_enabled: bool
    shell_timeout_seconds: int = 30
    log_path: str = "audit.log"
    max_consecutive_actions: int = 10


# ---------------------------------------------------------------------------
# Self-Improvement
# ---------------------------------------------------------------------------


@dataclass
class ConfigProposal:
    """A proposed change to the agent's configuration."""

    description: str
    diff: str               # unified diff format
    old_config: dict
    new_config: dict
    requires_restart: bool = False


# ---------------------------------------------------------------------------
# Agent Planning
# ---------------------------------------------------------------------------


@dataclass
class ToolCall:
    """A single tool invocation within a task plan."""

    tool_name: str
    params: dict[str, Any]
    requires_confirmation: bool = False


@dataclass
class ToolResult:
    """Result returned after executing a ToolCall."""

    success: bool
    data: Any
    error: str | None = None
    tool_name: str = ""


@dataclass
class TaskPlan:
    """A plan produced by the Task Planner for a given instruction."""

    original_instruction: str
    steps: list[ToolCall]
    reasoning: str


@dataclass
class InteractionRecord:
    """One complete instruction–response pair in the session history."""

    instruction: str
    response: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    timestamp: str = ""  # ISO 8601


# ---------------------------------------------------------------------------
# Goal Evaluation
# ---------------------------------------------------------------------------


class GoalStatus:
    """Status constants for goal evaluation."""

    IN_PROGRESS: str = "in_progress"
    COMPLETED: str = "completed"
    FAILED: str = "failed"
    EXHAUSTED: str = "exhausted"


@dataclass
class GoalEvaluation:
    """Result of evaluating whether a goal has been achieved."""

    status: str  # GoalStatus constant
    confidence: float  # 0.0 - 1.0
    evidence: list[str] = field(default_factory=list)
    failure_reasons: list[str] = field(default_factory=list)
    should_replan: bool = False
    next_steps: list[str] = field(default_factory=list)
