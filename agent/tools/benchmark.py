"""
agent/tools/benchmark.py

Benchmark Tool — mengukur waktu eksekusi dan membandingkan performa kode/skrip sebelum dan sesudah perubahan.

Komponen utama:
- `BenchmarkTool`: Implementasi `ToolInterface` untuk benchmarking.
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path
from typing import Any

from agent.models.schemas import ToolResult


class BenchmarkTool:
    """Tool untuk benchmarking dan pengukuran durasi eksekusi kode.

    Mengimplementasikan `ToolInterface`.
    """

    name: str = "benchmark"
    description: str = (
        "Ukur waktu eksekusi (wall-clock duration dalam ms) dari cuplikan kode Python "
        "atau skrip untuk mengevaluasi performa."
    )
    input_schema: dict = {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "Cuplikan kode Python yang akan di-benchmark.",
            },
            "iterations": {
                "type": "integer",
                "description": "Jumlah iterasi pengujian (default: 3).",
                "default": 3,
            },
        },
        "required": ["code"],
    }
    output_schema: dict = {
        "type": "object",
        "properties": {
            "iterations": {"type": "integer"},
            "avg_time_ms": {"type": "number"},
            "min_time_ms": {"type": "number"},
            "max_time_ms": {"type": "number"},
            "total_time_ms": {"type": "number"},
        },
    }

    async def run(self, params: dict) -> ToolResult:
        code = str(params.get("code", "")).strip()
        if not code:
            return ToolResult(
                success=False,
                data=None,
                error="Parameter 'code' tidak boleh kosong.",
                tool_name=self.name,
            )

        iterations = max(1, min(int(params.get("iterations", 3)), 50))
        durations: list[float] = []

        for _ in range(iterations):
            t0 = time.perf_counter()
            try:
                exec_globals: dict[str, Any] = {}
                exec(code, exec_globals)
            except Exception as exc:
                return ToolResult(
                    success=False,
                    data=None,
                    error=f"Eksekusi benchmark gagal: {exc}",
                    tool_name=self.name,
                )
            t1 = time.perf_counter()
            durations.append((t1 - t0) * 1000.0)  # ms

        avg_ms = sum(durations) / len(durations)
        min_ms = min(durations)
        max_ms = max(durations)

        return ToolResult(
            success=True,
            data={
                "iterations": iterations,
                "avg_time_ms": round(avg_ms, 3),
                "min_time_ms": round(min_ms, 3),
                "max_time_ms": round(max_ms, 3),
                "total_time_ms": round(sum(durations), 3),
            },
            tool_name=self.name,
        )


__all__ = ["BenchmarkTool"]
