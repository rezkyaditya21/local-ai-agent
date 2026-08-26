"""
agent/tools/code_search.py

Code Search Tool — melakukan pencarian simbol, fungsi, kelas, dan pola regex di seluruh berkas kode proyek.

Komponen utama:
- `CodeSearchTool`: Implementasi `ToolInterface` untuk pencarian kode.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any

from agent.models.schemas import ToolResult

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Konstanta
# ---------------------------------------------------------------------------

MAX_MATCHES: int = 50
DEFAULT_IGNORE_DIRS: set[str] = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".venv",
    "venv",
    "node_modules",
    ".idea",
    ".vscode",
}

# ---------------------------------------------------------------------------
# CodeSearchTool
# ---------------------------------------------------------------------------


class CodeSearchTool:
    """Tool untuk pencarian simbol, fungsi, kelas, dan pola regex di berkas proyek.

    Mengimplementasikan `ToolInterface`.
    """

    name: str = "code_search"
    description: str = (
        "Cari simbol, fungsi, kelas, atau pola regex di seluruh berkas kode proyek. "
        "Mendukung operasi 'search_symbol', 'search_regex', dan 'find_files'."
    )
    input_schema: dict = {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": ["search_symbol", "search_regex", "find_files"],
                "description": "Operasi pencarian yang akan dijalankan.",
            },
            "query": {
                "type": "string",
                "description": "Nama simbol atau pola regex yang ingin dicari.",
            },
            "path": {
                "type": "string",
                "description": "Direktori atau file target pencarian (default: '.').",
            },
            "file_pattern": {
                "type": "string",
                "description": "Ekstensi/pola file yang dicari, misal '*.py' atau '*.toml' (opsional).",
            },
        },
        "required": ["operation"],
    }
    output_schema: dict = {
        "type": "object",
        "properties": {
            "operation": {"type": "string"},
            "query": {"type": "string"},
            "matches": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "file": {"type": "string"},
                        "line": {"type": "integer"},
                        "content": {"type": "string"},
                    },
                },
            },
        },
    }

    async def run(self, params: dict) -> ToolResult:
        operation = str(params.get("operation", "")).strip()
        query = str(params.get("query", "")).strip()
        root_path = Path(str(params.get("path", "."))).resolve()
        file_pattern = str(params.get("file_pattern", "")).strip()

        if not root_path.exists():
            return ToolResult(
                success=False,
                data=None,
                error=f"Path '{root_path}' tidak ditemukan.",
                tool_name=self.name,
            )

        try:
            if operation == "search_symbol":
                if not query:
                    return ToolResult(
                        success=False,
                        data=None,
                        error="Parameter 'query' wajib untuk search_symbol.",
                        tool_name=self.name,
                    )
                matches = self._search_symbol(root_path, query, file_pattern)
            elif operation == "search_regex":
                if not query:
                    return ToolResult(
                        success=False,
                        data=None,
                        error="Parameter 'query' wajib untuk search_regex.",
                        tool_name=self.name,
                    )
                matches = self._search_regex(root_path, query, file_pattern)
            elif operation == "find_files":
                matches = self._find_files(root_path, query or file_pattern or "*")
            else:
                return ToolResult(
                    success=False,
                    data=None,
                    error=f"Operasi '{operation}' tidak dikenal.",
                    tool_name=self.name,
                )

            return ToolResult(
                success=True,
                data={"operation": operation, "query": query, "matches": matches[:MAX_MATCHES]},
                tool_name=self.name,
            )
        except Exception as exc:
            _logger.error("CodeSearchTool error: %s", exc)
            return ToolResult(
                success=False,
                data=None,
                error=f"Pencarian kode gagal: {exc}",
                tool_name=self.name,
            )

    def _search_symbol(self, root: Path, symbol: str, pattern: str) -> list[dict[str, Any]]:
        """Cari definisi class/def/variabel untuk simbol tersebut."""
        regex_pattern = re.compile(rf"\b(class|def|async def|\b{re.escape(symbol)})\b.*", re.IGNORECASE)
        return self._scan_files(root, regex_pattern, pattern)

    def _search_regex(self, root: Path, pattern_str: str, pattern: str) -> list[dict[str, Any]]:
        """Cari ekspresi reguler pada berkas."""
        regex_pattern = re.compile(pattern_str)
        return self._scan_files(root, regex_pattern, pattern)

    def _find_files(self, root: Path, pattern_str: str) -> list[dict[str, Any]]:
        """Temukan nama berkas yang cocok dengan pola glob."""
        matches = []
        pattern = pattern_str if pattern_str else "*"
        for path in root.rglob(pattern):
            if any(part in DEFAULT_IGNORE_DIRS for part in path.parts):
                continue
            if path.is_file():
                matches.append({
                    "file": str(path.relative_to(root)),
                    "line": 0,
                    "content": f"File: {path.name} (Size: {path.stat().st_size} bytes)",
                })
                if len(matches) >= MAX_MATCHES:
                    break
        return matches

    def _scan_files(self, root: Path, regex: re.Pattern, pattern: str) -> list[dict[str, Any]]:
        matches = []
        file_glob = pattern if pattern else "*.py"

        for filepath in root.rglob(file_glob if "*" in file_glob else "*"):
            if any(part in DEFAULT_IGNORE_DIRS for part in filepath.parts):
                continue
            if not filepath.is_file():
                continue

            try:
                content = filepath.read_text(encoding="utf-8", errors="ignore")
                for idx, line in enumerate(content.splitlines(), start=1):
                    if regex.search(line):
                        matches.append({
                            "file": str(filepath.relative_to(root)),
                            "line": idx,
                            "content": line.strip()[:200],
                        })
                        if len(matches) >= MAX_MATCHES:
                            return matches
            except Exception:
                continue

        return matches


__all__ = ["CodeSearchTool"]
