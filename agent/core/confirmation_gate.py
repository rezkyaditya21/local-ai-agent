"""
agent/core/confirmation_gate.py

Mekanisme konfirmasi pengguna sebelum tindakan destruktif atau berisiko tinggi dieksekusi.

- Menampilkan detail operasi (tipe, deskripsi, diff opsional, perintah shell opsional).
- Menunggu input "y"/"n" dari pengguna dalam batas waktu 60 detik.
- Auto-cancel (kembalikan False) jika tidak ada respons dalam 60 detik.
- Mendukung injeksi `input_fn` agar dapat diuji tanpa blocking I/O.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Callable

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text

from agent.core.exceptions import AgentConfirmationTimeoutError

CONFIRMATION_TIMEOUT_SECONDS = 60


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class ConfirmationRequest:
    """Berisi semua informasi yang diperlukan untuk menampilkan permintaan konfirmasi.

    Attributes:
        operation_type: Kategori operasi, mis. "delete", "dml", "shell", "apply_change".
        description:    Deskripsi singkat dalam bahasa alami tentang apa yang akan dilakukan.
        diff:           Unified diff (opsional) untuk operasi perubahan konfigurasi.
        full_command:   Perintah shell lengkap (opsional) untuk operasi shell.
    """

    operation_type: str
    description: str
    diff: str | None = None
    full_command: str | None = None


# ---------------------------------------------------------------------------
# ConfirmationGate
# ---------------------------------------------------------------------------


class ConfirmationGate:
    """Menampilkan detail operasi berisiko tinggi dan meminta konfirmasi pengguna.

    Args:
        input_fn:  Callable tanpa argumen yang mengembalikan baris input pengguna.
                   Di-inject untuk keperluan pengujian; defaultnya menggunakan
                   ``asyncio.get_event_loop().run_in_executor(None, input, "")``
                   sehingga blocking ``input()`` tidak membekukan event loop.
        console:   Instance ``rich.console.Console``. Jika tidak disediakan, instance
                   baru dibuat secara otomatis.
    """

    def __init__(
        self,
        input_fn: Callable[[], str] | None = None,
        console: Console | None = None,
    ) -> None:
        self._input_fn = input_fn
        self._console = console or Console()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def request(self, req: ConfirmationRequest) -> bool:
        """Tampilkan detail operasi dan tunggu konfirmasi pengguna.

        Menampilkan:
        - Jenis dan deskripsi operasi.
        - Diff (jika disediakan) dengan syntax highlighting.
        - Perintah shell lengkap (jika disediakan).
        - Prompt "[y/n] " dengan batas waktu 60 detik.

        Returns:
            ``True``  jika pengguna mengetikkan "y" (case-insensitive).
            ``False`` jika pengguna mengetikkan "n", string kosong, atau waktu habis.

        Side effects:
            - Menampilkan pesan pembatalan ke konsol jika timeout terjadi.
            - Menangkap (dan mengabaikan) ``AgentConfirmationTimeoutError`` secara
              internal setelah mencatatnya, sesuai kontrak yang mengembalikan False
              alih-alih menyebarkan exception.
        """
        self._render(req)

        try:
            answer = await asyncio.wait_for(
                self._get_input(),
                timeout=CONFIRMATION_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            self._console.print(
                "\n[bold yellow]⚠ Operasi dibatalkan:[/bold yellow] "
                f"tidak ada respons dalam {CONFIRMATION_TIMEOUT_SECONDS} detik."
            )
            # Angkat exception internal untuk memberi sinyal pada Executor / caller,
            # tetapi tetap kembalikan False seperti yang dispesifikasikan.
            try:
                raise AgentConfirmationTimeoutError(
                    operation_type=req.operation_type,
                    timeout_seconds=CONFIRMATION_TIMEOUT_SECONDS,
                )
            except AgentConfirmationTimeoutError:
                # Tangkap supaya metode ini selalu mengembalikan bool.
                return False

        return answer.strip().lower() == "y"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _render(self, req: ConfirmationRequest) -> None:
        """Render seluruh panel konfirmasi ke konsol."""
        console = self._console

        # ---- header ----
        header = Text()
        header.append("⚠  Konfirmasi Operasi Berisiko Tinggi\n", style="bold red")
        header.append(f"Tipe  : ", style="bold")
        header.append(req.operation_type, style="yellow")
        header.append(f"\nDetail: ", style="bold")
        header.append(req.description)

        console.print(Panel(header, border_style="red", expand=False))

        # ---- diff (opsional) ----
        if req.diff:
            console.print("\n[bold]Perubahan (diff):[/bold]")
            syntax = Syntax(req.diff, "diff", theme="monokai", word_wrap=True)
            console.print(syntax)

        # ---- full_command (opsional) ----
        if req.full_command:
            console.print("\n[bold]Perintah yang akan dieksekusi:[/bold]")
            syntax = Syntax(req.full_command, "bash", theme="monokai", word_wrap=True)
            console.print(syntax)

    async def _get_input(self) -> str:
        """Tunggu satu baris input dari pengguna secara async.

        Menggunakan ``input_fn`` yang diinjeksikan jika tersedia, sehingga
        pengujian dapat meng-override tanpa harus memblokir event loop.
        """
        if self._input_fn is not None:
            # input_fn mungkin sinkron (untuk kemudahan pengujian) atau async.
            result = self._input_fn()
            if asyncio.iscoroutine(result):
                return await result
            return result  # type: ignore[return-value]

        # Default: jalankan blocking input() di thread pool agar tidak
        # membekukan event loop asyncio.
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: input("[y/n] "))
