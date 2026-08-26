"""
agent/tools/project_inspect.py

Project Inspect Tool — menganalisis struktur repositori, dependensi (pyproject.toml/requirements.txt), dan arsitektur proyek.

Komponen utama:
- `ProjectInspectTool`: Implementasi `ToolInterface` untuk analisis struktur proyek.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from agent.models.schemas import ToolResult


class ProjectInspectTool:
    """Tool untuk memeriksa struktur repositori dan dependensi proyek.

    Mengimplementasikan `ToolInterface`.
    """

    name: str = "project_inspect"
    description: str = (
        "Analisis struktur proyek: berkas konfigurasi (pyproject.toml), dependensi, "
        "modul Python, direktori tes, dan titik masuk (entry points)."
    )
    input_schema: dict = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path direktori proyek (default: '.').",
            },
        },
    }
    output_schema: dict = {
        "type": "object",
        "properties": {
            "project_name": {"type": "string"},
            "version": {"type": "string"},
            "dependencies": {"type": "array", "items": {"type": "string"}},
            "modules": {"type": "array", "items": {"type": "string"}},
            "test_directories": {"type": "array", "items": {"type": "string"}},
        },
    }

    async def run(self, params: dict) -> ToolResult:
        root = Path(str(params.get("path", "."))).resolve()

        pyproject_file = root / "pyproject.toml"
        dependencies: list[str] = []
        project_name = root.name
        version = "0.1.0"

        if pyproject_file.exists():
            try:
                with open(pyproject_file, "rb") as f:
                    data = tomllib.load(f)
                proj = data.get("project", {})
                project_name = proj.get("name", project_name)
                version = proj.get("version", version)
                dependencies = proj.get("dependencies", [])
            except Exception:
                pass

        modules = [
            p.name for p in root.iterdir()
            if p.is_dir() and (p / "__init__.py").exists() and not p.name.startswith(".")
        ]
        test_dirs = [
            p.name for p in root.iterdir()
            if p.is_dir() and "test" in p.name.lower() and not p.name.startswith(".")
        ]

        return ToolResult(
            success=True,
            data={
                "project_name": project_name,
                "version": version,
                "dependencies": dependencies,
                "modules": modules,
                "test_directories": test_dirs,
                "root": str(root),
            },
            tool_name=self.name,
        )


__all__ = ["ProjectInspectTool"]
