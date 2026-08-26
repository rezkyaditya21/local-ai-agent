"""
agent/tools/git_tool.py

Git Tool — mengelola status, diff, commit, log, checkpoint, dan rollback Git pada repositori.

Komponen utama:
- `GitTool`: Implementasi `ToolInterface` untuk operasi Git.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
from pathlib import Path
from typing import Any

from agent.models.schemas import ToolResult

_logger = logging.getLogger(__name__)


class GitTool:
    """Tool untuk mengelola repositori Git dan melakukan pemulihan/checkpoint.

    Mengimplementasikan `ToolInterface`.
    """

    name: str = "git"
    description: str = (
        "Operasi Git untuk memeriksa status, diff, commit, log, serta membuat "
        "checkpoint dan rollback pemulihan repositori."
    )
    input_schema: dict = {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": ["status", "diff", "commit", "log", "checkpoint", "rollback"],
                "description": "Operasi Git yang ingin dijalankan.",
            },
            "message": {
                "type": "string",
                "description": "Pesan commit atau nama checkpoint (opsional).",
            },
            "path": {
                "type": "string",
                "description": "Path repositori atau file spesifik (default: '.').",
            },
        },
        "required": ["operation"],
    }
    output_schema: dict = {
        "type": "object",
        "properties": {
            "operation": {"type": "string"},
            "output": {"type": "string"},
            "success": {"type": "boolean"},
        },
    }

    async def run(self, params: dict) -> ToolResult:
        operation = str(params.get("operation", "")).strip()
        message = str(params.get("message", "")).strip()
        repo_path = Path(str(params.get("path", "."))).resolve()

        if not shutil.which("git"):
            return ToolResult(
                success=False,
                data=None,
                error="Executable 'git' tidak terpasang di sistem PATH.",
                tool_name=self.name,
            )

        try:
            if operation == "status":
                out = await self._run_git(["status", "--short"], repo_path)
            elif operation == "diff":
                out = await self._run_git(["diff"], repo_path)
            elif operation == "log":
                out = await self._run_git(["log", "-n", "5", "--oneline"], repo_path)
            elif operation == "commit":
                if not message:
                    message = "Auto-commit by AI Agent"
                await self._run_git(["add", "-A"], repo_path)
                out = await self._run_git(["commit", "-m", message], repo_path)
            elif operation == "checkpoint":
                tag_name = f"checkpoint-{int(asyncio.get_event_loop().time())}"
                if message:
                    tag_name += f"-{message.replace(' ', '_')}"
                await self._run_git(["add", "-A"], repo_path)
                out = await self._run_git(["stash", "create"], repo_path)
                if not out.strip():
                    out = f"Checkpoint created: HEAD is clean ({tag_name})"
                else:
                    out = f"Checkpoint created with stash hash: {out.strip()}"
            elif operation == "rollback":
                # Stash hard reset / restore
                await self._run_git(["reset", "--hard", "HEAD"], repo_path)
                out = await self._run_git(["clean", "-fd"], repo_path)
                out = f"Rollback berhasil dikembalikan ke HEAD bersih.\n{out}"
            else:
                return ToolResult(
                    success=False,
                    data=None,
                    error=f"Operasi Git '{operation}' tidak dikenal.",
                    tool_name=self.name,
                )

            return ToolResult(
                success=True,
                data={"operation": operation, "output": out},
                tool_name=self.name,
            )
        except Exception as exc:
            _logger.error("GitTool error: %s", exc)
            return ToolResult(
                success=False,
                data=None,
                error=f"Operasi Git '{operation}' gagal: {exc}",
                tool_name=self.name,
            )

    async def _run_git(self, args: list[str], cwd: Path) -> str:
        cmd = ["git"] + args
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        out_str = stdout.decode("utf-8", errors="ignore")
        err_str = stderr.decode("utf-8", errors="ignore")
        if proc.returncode != 0 and err_str and "nothing to commit" not in err_str:
            raise RuntimeError(f"Git command '{' '.join(cmd)}' failed ({proc.returncode}): {err_str}")
        return out_str or err_str or "OK"


__all__ = ["GitTool"]
