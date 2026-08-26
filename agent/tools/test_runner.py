"""
agent/tools/test_runner.py

Test Runner Tool — menjalankan suite pengujian (pytest / unittest) dan mem-parse hasilnya.

Komponen utama:
- `TestRunnerTool`: Implementasi `ToolInterface` untuk mengeksekusi tes unit/integrasi.
"""

from __future__ import annotations

import asyncio
import logging
import re
import sys
from pathlib import Path
from typing import Any

from agent.models.schemas import ToolResult

_logger = logging.getLogger(__name__)


class TestRunnerTool:
    """Tool untuk menjalankan pytest atau unittest dan menangkap hasilnya.

    Mengimplementasikan `ToolInterface`.
    """

    name: str = "test_runner"
    description: str = (
        "Jalankan pengujian unit/integrasi (pytest) pada proyek dan dapatkan laporan "
        "hasil tes (passed, failed, tracebacks, error summary)."
    )
    input_schema: dict = {
        "type": "object",
        "properties": {
            "test_path": {
                "type": "string",
                "description": "Path ke file atau direktori tes (default: 'tests').",
            },
            "verbose": {
                "type": "boolean",
                "description": "Output verbose (-v). Default: false.",
            },
            "k_filter": {
                "type": "string",
                "description": "Filter nama tes spesifik (-k filter_expression) opsional.",
            },
        },
    }
    output_schema: dict = {
        "type": "object",
        "properties": {
            "passed": {"type": "integer"},
            "failed": {"type": "integer"},
            "total": {"type": "integer"},
            "success": {"type": "boolean"},
            "output": {"type": "string"},
            "failed_tests": {"type": "array", "items": {"type": "string"}},
        },
    }

    async def run(self, params: dict) -> ToolResult:
        test_path = str(params.get("test_path", "tests")).strip()
        verbose = bool(params.get("verbose", False))
        k_filter = str(params.get("k_filter", "")).strip()

        cmd = [sys.executable, "-m", "pytest", test_path]
        if verbose:
            cmd.append("-v")
        if k_filter:
            cmd.extend(["-k", k_filter])

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=Path.cwd(),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            output = stdout.decode("utf-8", errors="ignore") + "\n" + stderr.decode("utf-8", errors="ignore")

            parsed = self._parse_pytest_output(output)
            parsed["exit_code"] = proc.returncode

            return ToolResult(
                success=(proc.returncode == 0),
                data=parsed,
                error=None if proc.returncode == 0 else f"Pengujian gagal dengan exit code {proc.returncode}.",
                tool_name=self.name,
            )
        except Exception as exc:
            _logger.error("TestRunnerTool error: %s", exc)
            return ToolResult(
                success=False,
                data=None,
                error=f"Gagal menjalankan test runner: {exc}",
                tool_name=self.name,
            )

    def _parse_pytest_output(self, output: str) -> dict[str, Any]:
        passed = 0
        failed = 0
        total = 0
        failed_tests = []

        # Parse summary line: e.g., "131 passed, 1 warning in 2.33s"
        match_passed = re.search(r"(\d+)\s+passed", output)
        if match_passed:
            passed = int(match_passed.group(1))

        match_failed = re.search(r"(\d+)\s+failed", output)
        if match_failed:
            failed = int(match_failed.group(1))

        total = passed + failed

        # Parse failed test names: e.g., "FAILED tests/unit/test_foo.py::test_bar"
        for line in output.splitlines():
            if line.startswith("FAILED "):
                failed_tests.append(line.replace("FAILED ", "").strip())

        return {
            "passed": passed,
            "failed": failed,
            "total": total,
            "failed_tests": failed_tests,
            "output": output[-4000:] if len(output) > 4000 else output,
        }


__all__ = ["TestRunnerTool"]
