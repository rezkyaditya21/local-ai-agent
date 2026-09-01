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

    @classmethod
    def from_config(cls, config: dict) -> "ExecutionBudget":
        """Buat ExecutionBudget dari section [execution_budget] di config.toml.

        Jika section tidak ada, gunakan nilai default.

        Args:
            config: Dict konfigurasi utama (bukan section execution_budget saja).

        Returns:
            ExecutionBudget dengan nilai dari config atau default.
        """
        budget_section = config.get("execution_budget", {})
        return cls(
            max_iterations=budget_section.get("max_iterations", 15),
            max_tool_calls=budget_section.get("max_tool_calls", 50),
            max_runtime_seconds=budget_section.get("max_runtime_seconds", 300.0),
            max_tokens=budget_section.get("max_tokens", 32000),
            max_retries=budget_section.get("max_retries", 3),
        )

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
        if self.retry_count > 0 and self.retry_count >= self.max_retries:
            return True, f"Batas percobaan kembali (retries) tercapai ({self.retry_count}/{self.max_retries})"
        return False, "Budget masih tersedia"

    def consume_iteration(self) -> None:
        self.current_iteration += 1

    def consume_tool_call(self) -> None:
        self.current_tool_calls += 1

    def consume_tokens(self, count: int) -> None:
        self.consumed_tokens += count

    def increment_retry(self) -> None:
        self.retry_count += 1

    def reset_retry(self) -> None:
        self.retry_count = 0

    def remaining_summary(self) -> str:
        elapsed = time.time() - self.start_time
        rem_time = max(0.0, self.max_runtime_seconds - elapsed)
        rem_iter = max(0, self.max_iterations - self.current_iteration)
        rem_tools = max(0, self.max_tool_calls - self.current_tool_calls)
        return (
            f"Iterasi tersisa: {rem_iter} | "
            f"Tool calls tersisa: {rem_tools} | "
            f"Waktu tersisa: {rem_time:.1f}s | "
            f"Retries: {self.retry_count}/{self.max_retries}"
        )


__all__ = ["ExecutionBudget"]
