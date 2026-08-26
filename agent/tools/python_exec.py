"""
agent/tools/python_exec.py

Python Execution Tool — mengeksekusi skrip atau cuplikan kode Python secara aman dan menangkap stdout/stderr.

Komponen utama:
- `PythonExecTool`: Implementasi `ToolInterface` untuk eksekusi Python runtime.
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path
from typing import Any

from agent.models.schemas import ToolResult

DEFAULT_TIMEOUT_SECONDS: int = 15


class PythonExecTool:
    """Tool untuk menjalankan cuplikan kode Python secara aman di proses terpisah.

    Mengimplementasikan `ToolInterface`.
    """

    name: str = "python_exec"
    description: str = (
        "Eksekusi kode atau cuplikan skrip Python secara langsung dan tangkap "
        "stdout, stderr, serta nilai kembaliannya."
    )
    input_schema: dict = {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "Cuplikan kode Python yang akan dieksekusi.",
            },
            "timeout": {
                "type": "integer",
                "description": f"Batas waktu eksekusi dalam detik (default: {DEFAULT_TIMEOUT_SECONDS}).",
                "default": DEFAULT_TIMEOUT_SECONDS,
            },
        },
        "required": ["code"],
    }
    output_schema: dict = {
        "type": "object",
        "properties": {
            "stdout": {"type": "string"},
            "stderr": {"type": "string"},
            "exit_code": {"type": "integer"},
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

        timeout = int(params.get("timeout", DEFAULT_TIMEOUT_SECONDS))

        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", encoding="utf-8", delete=False) as tmp:
            tmp.write(code)
            tmp_path = Path(tmp.name)

        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable,
                str(tmp_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=float(timeout))
            except asyncio.TimeoutError:
                proc.kill()
                await proc.communicate()
                return ToolResult(
                    success=False,
                    data=None,
                    error=f"Eksekusi Python melebihi batas waktu {timeout} detik.",
                    tool_name=self.name,
                )

            out_str = stdout.decode("utf-8", errors="ignore")
            err_str = stderr.decode("utf-8", errors="ignore")

            return ToolResult(
                success=(proc.returncode == 0),
                data={
                    "stdout": out_str,
                    "stderr": err_str,
                    "exit_code": proc.returncode,
                },
                error=None if proc.returncode == 0 else f"Python execution error (exit {proc.returncode}): {err_str}",
                tool_name=self.name,
            )
        finally:
            if tmp_path.exists():
                tmp_path.unlink()


__all__ = ["PythonExecTool"]
