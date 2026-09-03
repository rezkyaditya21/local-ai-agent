"""
agent/tools/file_editor.py

Antigravity-Grade Surgical File Editor Tool for Local AI Agent.
Provides precise file reading, surgical search-and-replace, multi-block editing,
and safe atomic file writes.
"""

from __future__ import annotations

import difflib
from pathlib import Path
from typing import Any

from agent.models.schemas import ToolResult


class FileEditorTool:
    """Surgical file editor with diff, line slicing, and search-and-replace."""

    name: str = "file_editor"
    description: str = (
        "Tool pengedit berkas bedah tingkat lanjut: melihat berkas dengan nomor baris (view), "
        "membuat/menimpa berkas (write), mengganti potongan kode tertentu secara presisi (replace), "
        "dan melakukan patching diff."
    )
    input_schema: dict = {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": ["view", "write", "replace"],
                "description": "Operasi pengeditan berkas: 'view', 'write', atau 'replace'.",
            },
            "path": {
                "type": "string",
                "description": "Path absolut atau relatif ke berkas target.",
            },
            "content": {
                "type": "string",
                "description": "Konten baru untuk operasi 'write'.",
                "default": "",
            },
            "target_content": {
                "type": "string",
                "description": "Teks persis yang ingin dicari dan diganti untuk operasi 'replace'.",
                "default": "",
            },
            "replacement_content": {
                "type": "string",
                "description": "Teks pengganti untuk operasi 'replace'.",
                "default": "",
            },
            "start_line": {
                "type": "integer",
                "description": "Baris awal untuk operasi 'view' (1-indexed, opsional).",
            },
            "end_line": {
                "type": "integer",
                "description": "Baris akhir untuk operasi 'view' (1-indexed, opsional).",
            },
        },
        "required": ["operation", "path"],
    }
    output_schema: dict = {
        "type": "object",
        "properties": {
            "status": {"type": "string"},
            "diff": {"type": "string"},
        },
    }

    async def run(self, params: dict) -> ToolResult:
        """Eksekusi tool sesuai ToolInterface."""
        return await self.execute(**params)

    async def execute(self, **kwargs: Any) -> ToolResult:
        """Eksekusi operasi file_editor."""
        op = kwargs.get("operation")
        raw_path = kwargs.get("path", "")
        content = kwargs.get("content", "")
        target_content = kwargs.get("target_content", "")
        replacement_content = kwargs.get("replacement_content", "")
        start_line = kwargs.get("start_line")
        end_line = kwargs.get("end_line")

        if not raw_path:
            return ToolResult(success=False, data="", error="Path berkas wajib diisi.", tool_name=self.name)

        file_path = Path(raw_path).resolve()

        try:
            if op == "view":
                if not file_path.exists() or not file_path.is_file():
                    return ToolResult(success=False, data="", error=f"Berkas tidak ditemukan: {file_path}", tool_name=self.name)

                lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
                total_lines = len(lines)

                s = max(1, int(start_line)) if start_line else 1
                e = min(total_lines, int(end_line)) if end_line else total_lines

                sliced = lines[s - 1 : e]
                formatted = [f"{i:4d} | {line}" for i, line in enumerate(sliced, start=s)]
                output = f"=== File: {file_path.name} (Lines {s}-{e} of {total_lines}) ===\n" + "\n".join(formatted)
                return ToolResult(success=True, data=output, tool_name=self.name)

            elif op == "write":
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_text(content, encoding="utf-8")
                return ToolResult(
                    success=True,
                    data=f"Sukses menulis berkas: {file_path} ({len(content)} karakter)",
                    tool_name=self.name,
                )

            elif op == "replace":
                if not file_path.exists() or not file_path.is_file():
                    return ToolResult(success=False, data="", error=f"Berkas tidak ditemukan: {file_path}", tool_name=self.name)

                original = file_path.read_text(encoding="utf-8")
                if target_content not in original:
                    return ToolResult(
                        success=False,
                        data="",
                        error=f"'target_content' tidak ditemukan secara persis di dalam berkas {file_path.name}.",
                        tool_name=self.name,
                    )

                count = original.count(target_content)
                new_text = original.replace(target_content, replacement_content, 1)
                file_path.write_text(new_text, encoding="utf-8")

                diff = list(difflib.unified_diff(
                    original.splitlines(),
                    new_text.splitlines(),
                    fromfile="before",
                    tofile="after",
                    lineterm="",
                ))
                diff_summary = "\n".join(diff[:20])

                return ToolResult(
                    success=True,
                    data=f"Sukses mengganti konten pada {file_path.name} (ditemukan {count} kemunculan, diganti 1).\nDiff:\n{diff_summary}",
                    tool_name=self.name,
                )

            return ToolResult(success=False, data="", error=f"Operasi tidak dikenal: {op}", tool_name=self.name)

        except Exception as exc:
            return ToolResult(success=False, data="", error=f"Error file_editor: {exc}", tool_name=self.name)
