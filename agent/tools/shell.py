"""
agent/tools/shell.py

Shell Tool — menjalankan perintah shell, skrip, dan proses latar belakang.

Komponen utama:
- `DESTRUCTIVE_PATTERNS`: Daftar pola regex untuk perintah destruktif.
- `ShellTool`: Tool utama yang mengimplementasikan `ToolInterface`.

Requirements yang diimplementasikan: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

from agent.core.exceptions import AgentShellTimeoutError
from agent.models.schemas import BackgroundProcess, ShellResult, ToolResult

# ---------------------------------------------------------------------------
# Konstanta
# ---------------------------------------------------------------------------

DEFAULT_TIMEOUT_SECONDS = 30

# Pola regex untuk mendeteksi perintah destruktif (case-insensitive).
# Sesuai Requirement 3.4 dan design.md.
DESTRUCTIVE_PATTERNS: list[str] = [
    r"rm\s+-[rf]",      # rm -rf / rm -r / rm -f
    r"rmdir\s+/s",      # rmdir /s (Windows)
    r"format\s+",       # format C: / format /dev/...
    r"shutdown",        # shutdown (semua varian)
    r"del\s+/[fs]",     # del /f /s (Windows)
    r"mkfs\.",          # mkfs.ext4 / mkfs.vfat / dsb.
    r"dd\s+if=",        # dd if=... (disk duplication / zeroing)
]


# ---------------------------------------------------------------------------
# ShellTool
# ---------------------------------------------------------------------------


class ShellTool:
    """Tool untuk menjalankan perintah shell, skrip, dan proses latar belakang.

    Mengimplementasikan `ToolInterface` sehingga dapat didaftarkan ke
    `ToolRegistry` dan dipanggil oleh `Executor`.

    Attributes:
        name: Identifier unik tool.
        description: Deskripsi singkat untuk pemilihan otomatis oleh registry.
        input_schema: Skema parameter masukan (JSON Schema-compatible).
        output_schema: Skema nilai kembalian.
    """

    name: str = "shell"
    description: str = (
        "Menjalankan perintah shell, skrip (bash/PowerShell/Python), dan proses "
        "latar belakang; menangkap stdout dan stderr secara terpisah"
    )
    input_schema: dict = {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": ["run_command", "run_script", "start_background"],
                "description": "Operasi yang akan dijalankan",
            },
            "command": {
                "type": "string",
                "description": "Perintah shell (untuk run_command / start_background)",
            },
            "interpreter": {
                "type": "string",
                "description": "Interpreter untuk run_script (bash, python, pwsh, dsb.)",
            },
            "script_path": {
                "type": "string",
                "description": "Path ke file skrip (untuk run_script)",
            },
            "timeout": {
                "type": "integer",
                "description": f"Batas waktu eksekusi dalam detik (default: {DEFAULT_TIMEOUT_SECONDS})",
                "default": DEFAULT_TIMEOUT_SECONDS,
            },
        },
        "required": ["operation"],
    }
    output_schema: dict = {
        "oneOf": [
            {
                "title": "ShellResult",
                "type": "object",
                "properties": {
                    "exit_code": {"type": "integer"},
                    "stdout": {"type": "string"},
                    "stderr": {"type": "string"},
                    "timed_out": {"type": "boolean"},
                    "command": {"type": "string"},
                },
            },
            {
                "title": "BackgroundProcess",
                "type": "object",
                "properties": {
                    "pid": {"type": "integer"},
                    "command": {"type": "string"},
                    "status": {"type": "string"},
                    "exit_code": {"type": ["integer", "null"]},
                },
            },
        ]
    }

    # ------------------------------------------------------------------
    # ToolInterface: run()
    # ------------------------------------------------------------------

    async def run(self, params: dict) -> ToolResult:
        """Dispatcher utama untuk semua operasi ShellTool.

        Mendispatch ke method yang sesuai berdasarkan `params["operation"]`:
        - ``"run_command"``: jalankan perintah shell dan tunggu selesai.
        - ``"run_script"``: jalankan skrip dengan interpreter tertentu.
        - ``"start_background"``: jalankan proses di latar belakang.

        Args:
            params: Parameter operasi sesuai `input_schema`.

        Returns:
            `ToolResult` dengan `data` berisi `ShellResult` atau
            `BackgroundProcess`, atau `ToolResult(success=False)` jika gagal.
        """
        operation = params.get("operation")
        timeout = int(params.get("timeout", DEFAULT_TIMEOUT_SECONDS))

        try:
            if operation == "run_command":
                command = params.get("command", "")
                result = await self.run_command(command, timeout=timeout)
                return ToolResult(success=True, data=result, tool_name=self.name)

            elif operation == "run_script":
                interpreter = params.get("interpreter", "")
                script_path = params.get("script_path", "")
                result = await self.run_script(interpreter, script_path, timeout=timeout)
                return ToolResult(success=True, data=result, tool_name=self.name)

            elif operation == "start_background":
                command = params.get("command", "")
                proc = await self.start_background(command)
                return ToolResult(success=True, data=proc, tool_name=self.name)

            else:
                return ToolResult(
                    success=False,
                    data=None,
                    error=f"Operasi tidak dikenal: '{operation}'. "
                          f"Gunakan salah satu: run_command, run_script, start_background",
                    tool_name=self.name,
                )

        except AgentShellTimeoutError:
            # Biarkan AgentShellTimeoutError merambat ke Executor agar dapat
            # dilog dan dikembalikan sebagai ToolResult(success=False).
            raise

        except Exception as exc:  # noqa: BLE001
            return ToolResult(
                success=False,
                data=None,
                error=str(exc),
                tool_name=self.name,
            )

    # ------------------------------------------------------------------
    # Public methods
    # ------------------------------------------------------------------

    async def run_command(
        self,
        command: str,
        timeout: int = DEFAULT_TIMEOUT_SECONDS,
    ) -> ShellResult:
        """Eksekusi perintah shell dan kembalikan hasilnya.

        Stdout dan stderr ditangkap secara terpisah (tidak digabungkan).
        Jika melebihi `timeout` detik, proses di-kill dan
        `AgentShellTimeoutError` dilempar (Requirement 3.7).

        Args:
            command: Perintah shell yang akan dieksekusi.
            timeout: Batas waktu eksekusi dalam detik.

        Returns:
            `ShellResult` berisi `exit_code`, `stdout`, `stderr`,
            `timed_out`, dan `command`.

        Raises:
            AgentShellTimeoutError: Jika proses melebihi batas waktu.
        """
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(),
                timeout=float(timeout),
            )
        except asyncio.TimeoutError:
            # Kill proses dan tunggu sebentar agar resource dibersihkan.
            try:
                process.kill()
            except ProcessLookupError:
                pass  # Proses sudah berakhir
            # Drain output yang sudah tersedia sebelum raise.
            try:
                await asyncio.wait_for(process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                pass
            raise AgentShellTimeoutError(
                command=command,
                timeout_seconds=timeout,
            )

        return ShellResult(
            exit_code=process.returncode if process.returncode is not None else -1,
            stdout=stdout_bytes.decode("utf-8", errors="replace"),
            stderr=stderr_bytes.decode("utf-8", errors="replace"),
            timed_out=False,
            command=command,
        )

    async def run_script(
        self,
        interpreter: str,
        script_path: str,
        timeout: int = DEFAULT_TIMEOUT_SECONDS,
    ) -> ShellResult:
        """Jalankan skrip menggunakan interpreter yang ditentukan.

        Membangun perintah ``<interpreter> <script_path>`` dan mendelegasikan
        eksekusi ke `run_command`. Mendukung bash, python, pwsh, node, dsb.
        (Requirement 3.3).

        Args:
            interpreter: Interpreter yang akan digunakan (mis. "bash", "python3").
            script_path: Path ke file skrip yang akan dieksekusi.
            timeout: Batas waktu eksekusi dalam detik.

        Returns:
            `ShellResult` yang sama seperti `run_command`.

        Raises:
            AgentShellTimeoutError: Jika eksekusi skrip melebihi batas waktu.
        """
        # Kutip script_path untuk menangani spasi dalam path.
        command = f'{interpreter} "{script_path}"'
        result = await self.run_command(command, timeout=timeout)
        # Perbarui field `command` agar lebih deskriptif.
        result.command = command
        return result

    async def start_background(self, command: str) -> BackgroundProcess:
        """Jalankan perintah di latar belakang tanpa menunggu selesai.

        Proses diluncurkan segera dan dikembalikan tanpa menunggu output atau
        exit code (Requirement 3.5). PID yang valid dikembalikan bersama
        status awal ``"running"``.

        Args:
            command: Perintah shell yang akan dijalankan di latar belakang.

        Returns:
            `BackgroundProcess` berisi PID, command, status ``"running"``,
            dan `exit_code=None` (karena proses belum selesai).
        """
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        return BackgroundProcess(
            pid=process.pid,
            command=command,
            status="running",
            exit_code=None,
        )

    def is_destructive(self, command: str) -> bool:
        """Periksa apakah perintah cocok dengan salah satu pola destruktif.

        Pencocokan dilakukan dengan `re.search` (bukan full-match) agar pola
        yang muncul di tengah perintah panjang tetap terdeteksi. Pencocokan
        bersifat case-insensitive (Requirement 3.4).

        Args:
            command: Perintah shell yang akan diperiksa.

        Returns:
            ``True`` jika perintah mengandung pola destruktif,
            ``False`` jika tidak.
        """
        for pattern in DESTRUCTIVE_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                return True
        return False


__all__ = [
    "DEFAULT_TIMEOUT_SECONDS",
    "DESTRUCTIVE_PATTERNS",
    "ShellTool",
]
