"""
agent/core/budget.py

Execution Budget — mengelola anggaran eksekusi dinamis untuk menggantikan hard limit sederhana.

Komponen utama:
- `ExecutionBudget`: Pengelola anggaran eksekusi otonom.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ExecutionBudget:
    """Anggaran eksekusi untuk mengontrol siklus otonom agent."""

    max_iterations: int = 15
    max_tool_calls: int = 50
    max_runtime_seconds: float = 300.0
    max_tokens: int = 32000
    max_retries: int = 3

    current_iteration: int = 0
    current_tool_calls: int = 0
    start_time: float = field(default_factory=time.time)
    consumed_tokens: int = 0
    retry_count: int = 0

    def is_exhausted(self) -> tuple[bool, str]:
        """Periksa apakah ada batas anggaran yang sudah terlampaui."""
        if self.current_iteration >= self.max_iterations:
            return True, f"Batas iterasi maksimum tercapai ({self.current_iteration}/{self.max_iterations})"
        if self.current_tool_calls >= self.max_tool_calls:
            return True, f"Batas tool calls maksimum tercapai ({self.current_tool_calls}/{self.max_tool_calls})"
        elapsed = time.time() - self.start_time
        if elapsed >= self.max_runtime_seconds:
            return True, f"Batas waktu eksekusi maksimum tercapai ({elapsed:.1f}s/{self.max_runtime_seconds}s)"
        if self.consumed_tokens >= self.max_tokens:
            return True, f"Batas konsumsi token maksimum tercapai ({self.consumed_tokens}/{self.max_tokens})"
        if self.retry_count >= self.max_retries:
            return True, f"Batas percobaankembali (retries) tercapai ({self.retry_count}/{self.max_retries})"
        return False, "Budget masih tersedia"

    def consume_iteration(self) -> None:
        self.current_iteration += 1

    def consume_tool_call(self) -> None:
        self.current_tool_calls += 1

    def consume_tokens(self, count: int) -> None:
        self.consumed_tokens += count

    def increment_retry(self) -> None:
        self.retry_count += 1

    def remaining_summary(self) -> str:
        elapsed = time.time() - self.start_time
        rem_time = max(0.0, self.max_runtime_seconds - elapsed)
        rem_iter = max(0, self.max_iterations - self.current_iteration)
        return f"Iterasi tersisa: {rem_iter} | Waktu tersisa: {rem_time:.1f}s | Tool calls: {self.current_tool_calls}/{self.max_tool_calls}"


__all__ = ["ExecutionBudget"]
