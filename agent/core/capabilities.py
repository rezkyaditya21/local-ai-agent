"""
agent/core/capabilities.py

Capability Manager & Capability Map — menemukan dan menyimpan kemampuan aktual dari lingkungan runtime.

Komponen utama:
- `CapabilityMap`: Dataclass peta kemampuan aktual.
- `CapabilityManager`: Pengelola dan detektor kemampuan environment.
"""

from __future__ import annotations

import logging
import os
import platform
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_logger = logging.getLogger(__name__)


@dataclass
class CapabilityMap:
    """Peta kemampuan aktual lingkungan tempat Agent berjalan."""

    os_platform: str
    python_version: str
    has_git: bool
    has_pytest: bool
    has_playwright: bool
    has_node: bool
    has_npm: bool
    has_docker: bool
    has_ollama: bool
    installed_compilers: list[str] = field(default_factory=list)
    available_models: list[str] = field(default_factory=list)
    environment_variables: dict[str, str] = field(default_factory=dict)
    capabilities_status: dict[str, bool] = field(default_factory=dict)

    def is_available(self, capability_name: str) -> bool:
        """Periksa apakah kemampuan tertentu tersedia secara aktual."""
        return self.capabilities_status.get(capability_name.lower(), False)

    def to_prompt_context(self) -> str:
        """Generate teks ringkasan kemampuan untuk disuntikkan ke prompt."""
        lines = [
            f"OS: {self.os_platform}",
            f"Python: {self.python_version}",
            f"Git: {'Available' if self.has_git else 'Not available'}",
            f"Pytest: {'Available' if self.has_pytest else 'Not available'}",
            f"Playwright: {'Available' if self.has_playwright else 'Not available'}",
            f"Node.js: {'Available' if self.has_node else 'Not available'}",
            f"Docker: {'Available' if self.has_docker else 'Not available'}",
            f"Ollama: {'Available' if self.has_ollama else 'Not available'}",
        ]
        if self.installed_compilers:
            lines.append(f"Compilers: {', '.join(self.installed_compilers)}")
        if self.available_models:
            lines.append(f"Models: {', '.join(self.available_models)}")
        return " | ".join(lines)


class CapabilityManager:
    """Pengelola dan detektor kemampuan aktual environment."""

    def __init__(self) -> None:
        self._map: CapabilityMap | None = None

    def detect_capabilities(self, configured_models: list[str] | None = None) -> CapabilityMap:
        """Deteksi kemampuan aktual environment saat startup atau saat diminta."""
        has_git = shutil.which("git") is not None
        has_pytest = shutil.which("pytest") is not None or self._check_import("pytest")
        has_playwright = self._check_import("playwright")
        has_node = shutil.which("node") is not None
        has_npm = shutil.which("npm") is not None
        has_docker = shutil.which("docker") is not None
        has_ollama = shutil.which("ollama") is not None

        compilers = []
        for comp in ["gcc", "g++", "clang", "cl", "rustc", "go"]:
            if shutil.which(comp):
                compilers.append(comp)

        status = {
            "git": has_git,
            "pytest": has_pytest,
            "playwright": has_playwright,
            "node": has_node,
            "npm": has_npm,
            "docker": has_docker,
            "ollama": has_ollama,
            "python": True,
            "filesystem": True,
            "shell": True,
        }

        self._map = CapabilityMap(
            os_platform=platform.platform(),
            python_version=sys.version.split()[0],
            has_git=has_git,
            has_pytest=has_pytest,
            has_playwright=has_playwright,
            has_node=has_node,
            has_npm=has_npm,
            has_docker=has_docker,
            has_ollama=has_ollama,
            installed_compilers=compilers,
            available_models=configured_models or [],
            capabilities_status=status,
        )
        _logger.info(
            "Capabilities: %s | Python %s | Git=%s | Pytest=%s | Tools=%d",
            self._map.os_platform,
            self._map.python_version,
            has_git,
            has_pytest,
            sum(1 for v in status.values() if v),
        )
        return self._map

    def get_map(self) -> CapabilityMap:
        if self._map is None:
            return self.detect_capabilities()
        return self._map

    def _check_import(self, module_name: str) -> bool:
        try:
            __import__(module_name)
            return True
        except ImportError:
            return False


__all__ = ["CapabilityMap", "CapabilityManager"]
