"""
agent/core/system_inspector.py

System Inspector — menemukan kapabilitas lingkungan runtime, tools, pustaka, dan framework yang tersedia secara jujur.

Komponen utama:
- `SystemCapabilityReport`: Dataclass laporan kapabilitas sistem.
- `SystemInspector`: Penginspeksi otomatis environment.
"""

from __future__ import annotations

import logging
import os
import platform
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

_logger = logging.getLogger(__name__)


@dataclass
class SystemCapabilityReport:
    """Laporan kapabilitas jujur dari lingkungan tempat Agent berjalan."""

    python_version: str
    platform_os: str
    git_available: bool
    pytest_available: bool
    playwright_available: bool
    available_tools: list[str] = field(default_factory=list)
    project_root: str = ""
    has_virtualenv: bool = False

    def to_prompt_summary(self) -> str:
        """Sintesis ringkasan kapabilitas untuk disuntikkan ke prompt LLM."""
        lines = [
            f"OS: {self.platform_os}",
            f"Python: {self.python_version.split()[0]}",
            f"Git: {'Tersedia' if self.git_available else 'Tidak Ada'}",
            f"Pytest: {'Tersedia' if self.pytest_available else 'Tidak Ada'}",
            f"Playwright: {'Tersedia' if self.playwright_available else 'Tidak Ada'}",
            f"Tools Aktif: {', '.join(self.available_tools)}",
        ]
        return " | ".join(lines)


class SystemInspector:
    """Inspektur kapabilitas lingkungan runtime Agent."""

    def inspect(self, registered_tools: list[str] | None = None) -> SystemCapabilityReport:
        git_avail = shutil.which("git") is not None
        pytest_avail = shutil.which("pytest") is not None or self._can_import("pytest")
        playwright_avail = self._can_import("playwright")
        in_venv = sys.prefix != sys.base_prefix or "VIRTUAL_ENV" in os.environ

        return SystemCapabilityReport(
            python_version=sys.version,
            platform_os=platform.platform(),
            git_available=git_avail,
            pytest_available=pytest_avail,
            playwright_available=playwright_avail,
            available_tools=registered_tools or [],
            project_root=str(Path.cwd()),
            has_virtualenv=in_venv,
        )

    def _can_import(self, module_name: str) -> bool:
        try:
            __import__(module_name)
            return True
        except ImportError:
            return False


__all__ = ["SystemCapabilityReport", "SystemInspector"]
