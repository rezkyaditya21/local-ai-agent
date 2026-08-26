"""
agent/self_improvement/self_debugging.py

Self-Debugging Module — mengidentifikasi kelemahan internal pada proyek, tool, memori, atau pengelola eksekusi.

Komponen utama:
- `DebugReport`: Dataclass laporan hasil self-debugging.
- `SelfDebuggingModule`: Modul pelacak kelemahan dan pembuat perbaikan.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agent.memory.memory_system import MemorySystem
from agent.tools.registry import ToolRegistry

_logger = logging.getLogger(__name__)


@dataclass
class DebugReport:
    """Laporan analisis kelemahan internal sistem."""

    identified_weaknesses: list[str] = field(default_factory=list)
    proposed_fixes: list[str] = field(default_factory=list)
    failing_tools: list[str] = field(default_factory=list)


class SelfDebuggingModule:
    """Modul pelacak kelemahan internal dan pembuat rekomendasi patch."""

    def __init__(self, registry: ToolRegistry, memory_system: MemorySystem) -> None:
        self._registry = registry
        self._memory = memory_system

    def analyze_system_health(self) -> DebugReport:
        """Analisis kesehatan internal sistem berdasarkan Self Knowledge dan status tool."""
        weaknesses = []
        fixes = []
        failing_tools = []

        # Periksa catatan pola kegagalan tool di Self Knowledge
        failures = self._memory.get_self_knowledge("tool_failure_patterns", {})
        for tool_name, count in failures.items():
            if count >= 3:
                weaknesses.append(f"Tool '{tool_name}' mengalami kegagalan berulang ({count}x).")
                fixes.append(f"Periksa skema masukan dan penanganan eksepsi pada agent/tools/{tool_name}.py")
                failing_tools.append(tool_name)

        if not weaknesses:
            weaknesses.append("Sistem berjalan sehat tanpa pola kegagalan berulang.")

        return DebugReport(
            identified_weaknesses=weaknesses,
            proposed_fixes=fixes,
            failing_tools=failing_tools,
        )


__all__ = ["DebugReport", "SelfDebuggingModule"]
