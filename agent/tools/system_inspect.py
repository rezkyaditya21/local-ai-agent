"""
agent/tools/system_inspect.py

System Inspect Tool — memeriksa lingkungan runtime, OS, Python version, paket terinstal, dan status sistem.

Komponen utama:
- `SystemInspectTool`: Implementasi `ToolInterface` untuk inspeksi lingkungan.
"""

from __future__ import annotations

import os
import platform
import sys
from pathlib import Path
from typing import Any

from agent.models.schemas import ToolResult


class SystemInspectTool:
    """Tool untuk memeriksa kemampuan lingkungan runtime dan OS.

    Mengimplementasikan `ToolInterface`.
    """

    name: str = "system_inspect"
    description: str = (
        "Inspeksi kemampuan lingkungan runtime: versi Python, platform OS, "
        "paket terinstal, variabel lingkungan, dan direktori kerja."
    )
    input_schema: dict = {
        "type": "object",
        "properties": {
            "target": {
                "type": "string",
                "enum": ["all", "runtime", "packages", "env"],
                "description": "Target inspeksi (default: 'all').",
                "default": "all",
            },
        },
    }
    output_schema: dict = {
        "type": "object",
        "properties": {
            "python_version": {"type": "string"},
            "platform": {"type": "string"},
            "executable": {"type": "string"},
            "cwd": {"type": "string"},
            "installed_packages": {"type": "array", "items": {"type": "string"}},
        },
    }

    async def run(self, params: dict) -> ToolResult:
        target = str(params.get("target", "all")).strip()

        data: dict[str, Any] = {
            "python_version": sys.version,
            "platform": platform.platform(),
            "executable": sys.executable,
            "cwd": str(Path.cwd()),
        }

        if target in ("all", "packages"):
            data["installed_packages"] = self._get_installed_packages()

        if target in ("all", "env"):
            data["env_keys"] = sorted([k for k in os.environ.keys() if "KEY" not in k and "PASS" not in k and "TOKEN" not in k and "SECRET" not in k])

        return ToolResult(
            success=True,
            data=data,
            tool_name=self.name,
        )

    def _get_installed_packages(self) -> list[str]:
        try:
            import pkg_resources
            return sorted([f"{d.project_name}=={d.version}" for d in pkg_resources.working_set])[:100]
        except Exception:
            try:
                import importlib.metadata
                return sorted([f"{dist.metadata['Name']}=={dist.version}" for dist in importlib.metadata.distributions()])[:100]
            except Exception:
                return ["(gagal membaca paket terinstal)"]


__all__ = ["SystemInspectTool"]
