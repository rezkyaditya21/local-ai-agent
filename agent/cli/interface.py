"""
agent/cli/interface.py

CLI — Antarmuka terminal interaktif untuk Local AI Agent.

Fitur utama:
- Loop REPL utama dengan validasi panjang input (≤32.000 karakter).
- Built-in commands: /help, /stop, /history, /model, /tools, /rollback, /clear.
- Spinner animasi setiap 200ms saat Agent memproses.
- Streaming token dengan syntax highlighting untuk blok kode.
- Integrasi penuh dengan Agent, ModelManager, ToolRegistry, dan
  SelfImprovementModule.

Requirements yang diimplementasikan: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7,
                                      1.8, 1.9, 1.10, 1.11
"""

from __future__ import annotations

import asyncio
import re
import sys
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, AsyncIterator

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.spinner import Spinner
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text
from rich.live import Live

if TYPE_CHECKING:
    from agent.core.orchestrator import Agent
    from agent.models.manager import ModelManager
    from agent.models.schemas import InteractionRecord
    from agent.self_improvement.module import SelfImprovementModule
    from agent.tools.registry import ToolRegistry

# ---------------------------------------------------------------------------
# Konstanta
# ---------------------------------------------------------------------------

MAX_INPUT_LENGTH: int = 32_000
SPINNER_INTERVAL_MS: float = 200.0  # ms — diperbarui setiap 200ms (Req 1.3)

# Pola untuk mendeteksi blok kode Markdown ```lang ... ```
_CODE_BLOCK_PATTERN = re.compile(
    r"```(?P<lang>[a-zA-Z0-9_+-]*)\n(?P<code>.*?)```",
    re.DOTALL,
)

# Nama spinner Rich yang digunakan
_SPINNER_NAME = "dots"


# ---------------------------------------------------------------------------
# CLIConfig
# ---------------------------------------------------------------------------


@dataclass
class CLIConfig:
    """Konfigurasi CLI yang diambil dari argumen baris perintah.

    Attributes:
        model:         Nama model dari flag ``--model`` (atau ``None`` untuk
                       menggunakan default dari konfigurasi).
        history_limit: Jumlah maksimum pasangan instruksi-respons yang
                       ditampilkan oleh /history.
    """

    model: str | None = None
    history_limit: int = 1000


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


class CLI:
    """Antarmuka terminal interaktif untuk Local AI Agent.

    Menyediakan REPL loop, rendering output dengan Rich, penanganan
    built-in commands, dan integrasi dengan semua subsistem Agent.

    Args:
        config:                  Konfigurasi CLI.
        agent:                   Instansi Agent Orchestrator.
        model_manager:           Instansi ModelManager untuk /model commands.
        registry:                Instansi ToolRegistry untuk /tools commands.
        self_improvement_module: Instansi SelfImprovementModule untuk /rollback.
        console:                 Instansi Rich Console (dibuat otomatis jika None).
    """

    def __init__(
        self,
        config: CLIConfig,
        agent: "Agent",
        model_manager: "ModelManager",
        registry: "ToolRegistry",
        self_improvement_module: "SelfImprovementModule | None" = None,
        console: Console | None = None,
        scheduler: Any | None = None,
        gateway: Any | None = None,
    ) -> None:
        self._config = config
        self._agent = agent
        self._model_manager = model_manager
        self._registry = registry
        self._sim = self_improvement_module
        self._console = console or Console(force_terminal=True, legacy_windows=False)
        self._scheduler = scheduler
        self._gateway = gateway
        self._running: bool = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def validate_input_length(self, text: str) -> bool:
        """Kembalikan True jika panjang teks ≤ 32.000 karakter.

        Args:
            text: Teks yang akan divalidasi.

        Returns:
            ``True`` jika ``len(text) <= 32_000``; ``False`` jika melebihi batas.
        """
        return len(text) <= MAX_INPUT_LENGTH

    async def run(self) -> None:
        """Loop utama REPL.

        Alur per iterasi:
        1. Baca input pengguna (async via executor).
        2. Jika input adalah command (/help, /stop, dsb.), tangani dan lanjutkan.
        3. Validasi panjang input; tampilkan error jika melebihi batas.
        4. Tampilkan spinner, kirim ke Agent, render streaming respons.
        5. Ulangi sampai pengguna memanggil /stop atau EOF.
        """
        self._running = True
        self._show_welcome()

        loop = asyncio.get_event_loop()

        while self._running:
            # ---- baca input ----
            try:
                raw = await loop.run_in_executor(
                    None, lambda: self._console.input("\n[bold cyan]> [/bold cyan]")
                )
            except (EOFError, KeyboardInterrupt):
                # Ctrl+C atau EOF → hentikan
                await self._do_stop(graceful=True)
                break

            text = raw.strip()
            if not text:
                continue

            # ---- built-in commands ----
            is_cmd = await self.handle_command(text)
            if is_cmd:
                continue

            # ---- validasi panjang ----
            if not self.validate_input_length(text):
                self._console.print(
                    f"[bold red]⚠  Input terlalu panjang:[/bold red] "
                    f"{len(text):,} karakter (batas: {MAX_INPUT_LENGTH:,}). "
                    f"Harap persingkat instruksi Anda."
                )
                continue

            # ---- proses instruksi via Agent ----
            await self._process_instruction(text)

    async def handle_command(self, text: str) -> bool:
        """Tangani built-in commands dan kembalikan True jika teks adalah command.

        Commands yang didukung:
        - ``/help``                        — tampilkan semua commands
        - ``/stop``                        — hentikan sesi
        - ``/history``                     — tampilkan riwayat sesi
        - ``/clear``                       — bersihkan layar
        - ``/model list``                  — daftar semua model
        - ``/model use <name>``            — ganti model aktif
        - ``/tools list``                  — daftar semua tools
        - ``/tools enable <name>``         — aktifkan tool
        - ``/tools disable <name>``        — nonaktifkan tool
        - ``/rollback``                    — rollback konfigurasi

        Args:
            text: Teks yang dimasukkan pengguna.

        Returns:
            ``True`` jika teks dikenali sebagai command dan sudah ditangani;
            ``False`` jika bukan command (instruksi biasa).
        """
        if not text.startswith("/"):
            return False

        parts = text.split()
        cmd = parts[0].lower()

        # /help
        if cmd == "/help":
            self._show_help()
            return True

        # /stop
        if cmd == "/stop":
            await self._do_stop(graceful=True)
            return True

        # /history
        if cmd == "/history":
            history = self._agent.get_history()
            self.show_history(history)
            return True

        # /clear
        if cmd == "/clear":
            self._console.clear()
            return True

        # /model list
        if cmd == "/model" and len(parts) >= 2 and parts[1].lower() == "list":
            self._show_model_list()
            return True

        # /model use <name>
        if cmd == "/model" and len(parts) >= 2 and parts[1].lower() == "use":
            if len(parts) < 3:
                self._console.print(
                    "[bold red]Penggunaan:[/bold red] /model use <nama-model>"
                )
                return True
            model_name = parts[2]
            await self._switch_model(model_name)
            return True

        # /model (tanpa subcommand)
        if cmd == "/model":
            self._console.print(
                "[yellow]Subcommand /model yang tersedia:[/yellow] list, use <nama>"
            )
            return True

        # /tools list
        if cmd == "/tools" and len(parts) >= 2 and parts[1].lower() == "list":
            self._show_tools_list()
            return True

        # /tools enable <name>
        if cmd == "/tools" and len(parts) >= 2 and parts[1].lower() == "enable":
            if len(parts) < 3:
                self._console.print(
                    "[bold red]Penggunaan:[/bold red] /tools enable <nama-tool>"
                )
                return True
            self._toggle_tool(parts[2], enable=True)
            return True

        # /tools disable <name>
        if cmd == "/tools" and len(parts) >= 2 and parts[1].lower() == "disable":
            if len(parts) < 3:
                self._console.print(
                    "[bold red]Penggunaan:[/bold red] /tools disable <nama-tool>"
                )
                return True
            self._toggle_tool(parts[2], enable=False)
            return True

        # /tools (tanpa subcommand)
        if cmd == "/tools":
            self._console.print(
                "[yellow]Subcommand /tools yang tersedia:[/yellow] list, enable <nama>, disable <nama>"
            )
            return True

        # /rollback
        if cmd == "/rollback":
            await self._do_rollback()
            return True

        # /autonomous <goal> atau /auto <goal>
        if cmd in ("/autonomous", "/auto"):
            if len(parts) < 2:
                self._console.print(
                    "[bold red]Penggunaan:[/bold red] /autonomous <goal>"
                )
                return True
            goal = " ".join(parts[1:])
            await self._process_autonomous(goal)
            return True

        # /skill
        if cmd == "/skill":
            if len(parts) >= 2 and parts[1].lower() == "list":
                self._show_skills_list()
                return True
            if len(parts) >= 3 and parts[1].lower() == "info":
                self._show_skill_info(parts[2])
                return True
            if len(parts) >= 4 and parts[1].lower() == "create":
                name = parts[2]
                instructions = " ".join(parts[3:])
                self._create_skill(name, instructions)
                return True
            self._console.print(
                "[yellow]Subcommand /skill yang tersedia:[/yellow] list, info <nama>, create <nama> <instruksi>"
            )
            return True

        # /cron
        if cmd == "/cron":
            if len(parts) >= 2 and parts[1].lower() == "list":
                self._show_cron_list()
                return True
            if len(parts) >= 4 and parts[1].lower() == "add":
                name = parts[2]
                try:
                    interval = int(parts[3])
                except ValueError:
                    interval = 3600
                goal = " ".join(parts[4:]) if len(parts) > 4 else name
                self._add_cron_task(name, interval, goal)
                return True
            if len(parts) >= 3 and parts[1].lower() == "remove":
                self._remove_cron_task(parts[2])
                return True
            self._console.print(
                "[yellow]Subcommand /cron yang tersedia:[/yellow] list, add <nama> <interval_detik> <goal>, remove <id>"
            )
            return True

        # /gateway
        if cmd == "/gateway":
            self._show_gateway_status()
            return True

        # /memory
        if cmd == "/memory":
            if len(parts) >= 3 and parts[1].lower() == "search":
                query = " ".join(parts[2:])
                self._search_memory(query)
                return True
            self._show_memory()
            return True

        # /debug
        if cmd == "/debug":
            await self._show_debug()
            return True

        # Command tidak dikenal yang dimulai dengan /
        self._console.print(
            f"[bold red]Command tidak dikenal:[/bold red] '{cmd}'. "
            f"Ketik [bold]/help[/bold] untuk daftar lengkap."
        )
        return True

    async def render_stream(self, token_stream: "AsyncIterator[str]") -> str:
        """Render token stream secara real-time dan kembalikan teks lengkapnya.

        Token dikumpulkan dan ditampilkan langsung ke konsol menggunakan
        ``Console.print`` karakter demi karakter. Setelah stream selesai,
        teks lengkap diproses untuk syntax highlighting blok kode.

        Args:
            token_stream: Iterator async yang memproduksi token string.

        Returns:
            Teks lengkap yang dihasilkan dari semua token.
        """
        collected: list[str] = []

        # Cetak token secara streaming (tanpa newline agar tidak putus-putus)
        async for token in token_stream:
            self._console.print(token, end="", highlight=False)
            collected.append(token)

        full_text = "".join(collected)

        # Tutup baris terakhir
        self._console.print()

        # Post-process: render blok kode dengan syntax highlighting
        self._render_code_blocks(full_text)

        return full_text

    def show_history(self, session_history: "list[InteractionRecord]") -> None:
        """Tampilkan semua pasangan instruksi-respons dari sesi aktif.

        Ditampilkan dari yang terlama ke terbaru (Requirement 1.9).
        Setiap pasangan dirender dalam panel dengan timestamp.

        Args:
            session_history: Daftar InteractionRecord dari Agent.get_history().
        """
        if not session_history:
            self._console.print(
                "[dim]Belum ada riwayat pada sesi ini.[/dim]"
            )
            return

        self._console.print(
            f"\n[bold]Riwayat Sesi[/bold] — {len(session_history)} interaksi\n"
        )

        limit = self._config.history_limit
        display = session_history[-limit:] if len(session_history) > limit else session_history

        for i, record in enumerate(display, start=1):
            ts = record.timestamp or "—"
            # Header instruksi
            self._console.print(
                f"[bold cyan]--- [{i}/{len(session_history)}] {ts}[/bold cyan]"
            )
            self._console.print(
                f"[bold cyan]|[/bold cyan] [bold]Instruksi:[/bold] {record.instruction}"
            )
            self._console.print(f"[bold cyan]|[/bold cyan] [bold]Respons:[/bold]")

            # Tampilkan respons dengan batas panjang
            resp = record.response
            if len(resp) > 2000:
                resp = resp[:2000] + "\n[dim]... (dipotong)[/dim]"
            self._console.print(f"[bold cyan]|[/bold cyan] {resp}")

            if record.tool_calls:
                tools_used = ", ".join(tc.tool_name for tc in record.tool_calls)
                self._console.print(
                    f"[bold cyan]|[/bold cyan] [dim]Tools: {tools_used}[/dim]"
                )

            self._console.print("[bold cyan]---[/bold cyan]")

    def show_spinner(self, active: bool) -> None:
        """Tampilkan atau matikan indikator spinner secara sinkron.

        Metode ini menyediakan antarmuka sederhana yang kompatibel dengan
        konteks non-async. Untuk spinner yang sebenarnya (digunakan selama
        pemrosesan Agent), lihat ``_process_instruction``.

        Args:
            active: ``True`` untuk menampilkan pesan spinner; ``False`` untuk
                    menampilkan pesan selesai.
        """
        if active:
            self._console.print("[dim]⏳ Sedang memproses...[/dim]", end="\r")
        else:
            self._console.print("                        ", end="\r")  # bersihkan baris

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _show_welcome(self) -> None:
        """Tampilkan banner selamat datang dengan nama model aktif (Req 1.5)."""
        active = self._model_manager.get_active_model()
        model_display = active.name if active else "tidak ada model aktif"

        self._console.print(
            Panel(
                Text.assemble(
                    ("Local AI Agent", "bold white"),
                    ("\n", ""),
                    ("Model aktif: ", "dim"),
                    (model_display, "bold cyan"),
                    ("\n", ""),
                    ("Ketik ", "dim"),
                    ("/help", "bold"),
                    (" untuk daftar perintah, ", "dim"),
                    ("/stop", "bold"),
                    (" untuk keluar.", "dim"),
                ),
                title="[bold green]AI Agent[/bold green]",
                border_style="green",
            )
        )

    def _show_help(self) -> None:
        """Tampilkan tabel semua built-in commands (Req 1.6)."""
        table = Table(title="Perintah Bawaan", show_header=True, header_style="bold cyan")
        table.add_column("Perintah", style="bold yellow", no_wrap=True)
        table.add_column("Deskripsi")

        commands = [
            ("/help", "Tampilkan daftar semua perintah bawaan ini"),
            ("/stop", "Hentikan semua operasi dan akhiri sesi (juga: Ctrl+C)"),
            ("/history", "Tampilkan seluruh riwayat instruksi dan respons sesi ini"),
            ("/clear", "Bersihkan layar terminal"),
            ("/model list", "Tampilkan daftar semua model yang terdaftar"),
            ("/model use <nama>", "Ganti model AI yang aktif tanpa restart"),
            ("/tools list", "Tampilkan semua tool beserta status aktif/nonaktif"),
            ("/tools enable <nama>", "Aktifkan tool yang sedang dinonaktifkan"),
            ("/tools disable <nama>", "Nonaktifkan tool tanpa menghapusnya"),
            ("/skill list", "Lihat semua skill otonom yang terpasang"),
            ("/skill info <nama>", "Lihat detail petunjuk dan trigger dari suatu skill"),
            ("/skill create <nama> <instruksi>", "Buat skill baru secara manual"),
            ("/cron list", "Lihat daftar tugas latar belakang terjadwal"),
            ("/cron add <nama> <interval_detik> <goal>", "Tambah tugas otonom terjadwal"),
            ("/cron remove <id>", "Hapus tugas terjadwal"),
            ("/gateway", "Periksa status gateway Telegram"),
            ("/memory", "Tampilkan status ringkasan memori agent"),
            ("/memory search <query>", "Cari riwayat dan pengetahuan via SQLite FTS5"),
            ("/autonomous <goal>", "Jalankan agent dalam mode otonom penuh (closed-loop)"),
            ("/auto <goal>", "Alias untuk /autonomous"),
            ("/debug", "Tampilkan laporan kesehatan sistem"),
            ("/rollback", "Pulihkan konfigurasi Agent ke versi backup terakhir"),
        ]

        for cmd, desc in commands:
            table.add_row(cmd, desc)

        self._console.print(table)

    def _show_skills_list(self) -> None:
        """Tampilkan daftar semua skill otonom."""
        skill_manager = getattr(self._agent, "skill_manager", None)
        if not skill_manager:
            self._console.print("[dim]Skill Manager tidak aktif.[/dim]")
            return

        skills = skill_manager.list_skills()
        if not skills:
            self._console.print("[dim]Belum ada skill yang terpasang di folder ./skills/[/dim]")
            return

        table = Table(title="Daftar Skill Otonom", show_header=True, header_style="bold cyan")
        table.add_column("Nama Skill", style="bold green")
        table.add_column("Triggers")
        table.add_column("Deskripsi")

        for s in skills:
            trigs = ", ".join(s.triggers) if s.triggers else "-"
            desc = s.description[:50] + "..." if len(s.description) > 50 else s.description
            table.add_row(s.name, trigs, desc)

        self._console.print(table)

    def _show_skill_info(self, name: str) -> None:
        """Tampilkan detail satu skill."""
        skill_manager = getattr(self._agent, "skill_manager", None)
        if not skill_manager:
            return
        skill = skill_manager.get_skill(name)
        if not skill:
            self._console.print(f"[bold red]✗[/bold red] Skill '{name}' tidak ditemukan.")
            return

        self._console.print(Panel(skill.to_markdown(), title=f"[bold green]Skill: {skill.name}[/bold green]"))

    def _create_skill(self, name: str, instructions: str) -> None:
        """Buat skill baru."""
        skill_creator = getattr(self._agent, "skill_creator", None)
        if not skill_creator:
            self._console.print("[bold red]✗[/bold red] Skill Creator tidak tersedia.")
            return
        skill = skill_creator.create_skill_from_task(
            task_name=name,
            goal=instructions,
            steps=[instructions],
        )
        self._console.print(f"[bold green]✓[/bold green] Skill [bold]{skill.name}[/bold] berhasil dibuat dan disimpan di ./skills/")

    def _show_cron_list(self) -> None:
        """Tampilkan daftar tugas terjadwal."""
        if not self._scheduler:
            self._console.print("[dim]Task Scheduler belum diinisialisasi.[/dim]")
            return
        tasks = self._scheduler.list_tasks()
        if not tasks:
            self._console.print("[dim]Belum ada tugas terjadwal.[/dim]")
            return

        table = Table(title="Tugas Terjadwal (Cron)", show_header=True, header_style="bold cyan")
        table.add_column("ID", style="bold yellow")
        table.add_column("Nama")
        table.add_column("Interval (dtk)")
        table.add_column("Status Terakhir")
        table.add_column("Tujuan / Goal")

        for t in tasks:
            table.add_row(t.id, t.name, str(t.interval_seconds), t.last_status, t.goal[:40])

        self._console.print(table)

    def _add_cron_task(self, name: str, interval: int, goal: str) -> None:
        """Tambah tugas terjadwal baru."""
        if not self._scheduler:
            self._console.print("[bold red]✗[/bold red] Task Scheduler belum diinisialisasi.")
            return
        task = self._scheduler.add_task(name=name, goal=goal, interval_seconds=interval)
        self._console.print(f"[bold green]✓[/bold green] Tugas terjadwal [bold]{task.name}[/bold] (ID: {task.id}) berhasil ditambahkan (setiap {interval}s).")

    def _remove_cron_task(self, task_id: str) -> None:
        """Hapus tugas terjadwal."""
        if not self._scheduler:
            return
        if self._scheduler.remove_task(task_id):
            self._console.print(f"[bold green]✓[/bold green] Tugas {task_id} berhasil dihapus.")
        else:
            self._console.print(f"[bold red]✗[/bold red] Tugas {task_id} tidak ditemukan.")

    def _search_memory(self, query: str) -> None:
        """Cari riwayat dan fakta menggunakan SQLite FTS5."""
        memory = getattr(self._agent, "_memory", None)
        if not memory:
            return
        results = memory.search_fts(query, limit=5)
        if not results:
            self._console.print(f"[dim]Tidak ditemukan entri yang cocok dengan '{query}' di FTS5.[/dim]")
            return

        table = Table(title=f"Hasil Pencarian Memori: '{query}'", show_header=True, header_style="bold cyan")
        table.add_column("Kategori", style="bold magenta")
        table.add_column("Judul / Key", style="bold")
        table.add_column("Isi Konten")

        for r in results:
            content_preview = r.content[:80] + "..." if len(r.content) > 80 else r.content
            table.add_row(r.category, r.title, content_preview)

        self._console.print(table)

    def _show_gateway_status(self) -> None:
        """Tampilkan status gateway pesan."""
        if not self._gateway:
            self._console.print(Panel(
                "Telegram Gateway: [bold red]Nonaktif / Belum Dikonfigurasi[/bold red]\n"
                "Untuk mengaktifkan, tambahkan token bot di [bold]config.toml[/bold]:\n"
                "[gateway.telegram]\nenabled = true\ntoken = \"BOT_TOKEN_ANDA\"",
                title="[bold cyan]Status Gateway[/bold cyan]",
            ))
            return
        status_str = "[bold green]Aktif & Polling[/bold green]" if self._gateway._running else "[yellow]Dikonfigurasi (Standby)[/yellow]"
        self._console.print(Panel(
            f"Telegram Gateway: {status_str}\n"
            f"Allowed Users Whitelist: {len(self._gateway._allowed_user_ids)} ID terdaftar",
            title="[bold cyan]Status Gateway[/bold cyan]",
        ))

    def _show_model_list(self) -> None:
        """Tampilkan daftar model terdaftar (Req 7.3)."""
        models = self._model_manager.list_models()
        active = self._model_manager.get_active_model()
        active_name = active.name if active else None

        if not models:
            self._console.print("[dim]Tidak ada model terdaftar dalam konfigurasi.[/dim]")
            return

        table = Table(title="Model Terdaftar", show_header=True, header_style="bold cyan")
        table.add_column("Nama", style="bold")
        table.add_column("Tipe")
        table.add_column("Path / URL")
        table.add_column("Status")

        for m in models:
            status = "[bold green]● Aktif[/bold green]" if m.name == active_name else "[dim]○ Tidak aktif[/dim]"
            size_info = ""
            if m.size_bytes is not None:
                size_mb = m.size_bytes / (1024 * 1024)
                size_info = f" ({size_mb:.0f} MB)"
            table.add_row(
                m.name,
                m.model_type,
                m.path_or_url + size_info,
                status,
            )

        self._console.print(table)

    async def _switch_model(self, name: str) -> None:
        """Ganti model aktif dengan spinner (Req 7.4)."""
        self._console.print(f"Mengganti model ke [bold]{name}[/bold]...")

        success = False
        error_msg: str | None = None

        with Live(
            Spinner(_SPINNER_NAME, text=f"Memuat model '{name}'..."),
            console=self._console,
            refresh_per_second=5,
            transient=True,
        ):
            try:
                from agent.core.exceptions import (
                    AgentModelNotFoundError,
                    AgentModelLoadTimeoutError,
                )
                await self._model_manager.switch_model(name)
                success = True
            except AgentModelNotFoundError as exc:
                error_msg = str(exc)
            except AgentModelLoadTimeoutError as exc:
                error_msg = str(exc)
            except Exception as exc:
                error_msg = f"Gagal mengganti model: {exc}"

        if success:
            self._console.print(
                f"[bold green]✓[/bold green] Model berhasil diganti ke [bold]{name}[/bold]."
            )
        else:
            self._console.print(
                f"[bold red]✗[/bold red] {error_msg}"
            )

    def _show_tools_list(self) -> None:
        """Tampilkan semua tool beserta statusnya (Req 9.4)."""
        entries = self._registry.list_all()

        if not entries:
            self._console.print("[dim]Tidak ada tool terdaftar.[/dim]")
            return

        table = Table(title="Tool Terdaftar", show_header=True, header_style="bold cyan")
        table.add_column("Nama", style="bold")
        table.add_column("Sumber")
        table.add_column("Deskripsi")
        table.add_column("Status")

        for entry in entries:
            status = (
                "[bold green]● Aktif[/bold green]"
                if entry.enabled
                else "[bold red]○ Nonaktif[/bold red]"
            )
            # Potong deskripsi agar tabel tidak terlalu lebar
            desc = entry.tool.description
            if len(desc) > 60:
                desc = desc[:57] + "..."
            table.add_row(entry.tool.name, entry.source, desc, status)

        self._console.print(table)

    def _toggle_tool(self, name: str, enable: bool) -> None:
        """Aktifkan atau nonaktifkan tool berdasarkan nama (Req 9.5)."""
        from agent.core.exceptions import AgentToolNotFoundError

        action = "diaktifkan" if enable else "dinonaktifkan"
        try:
            if enable:
                self._registry.enable(name)
            else:
                self._registry.disable(name)
            self._console.print(
                f"[bold green]✓[/bold green] Tool [bold]{name}[/bold] berhasil {action}."
            )
        except AgentToolNotFoundError:
            self._console.print(
                f"[bold red]✗[/bold red] Tool [bold]{name}[/bold] tidak ditemukan dalam registry."
            )

    async def _do_rollback(self) -> None:
        """Jalankan rollback via SelfImprovementModule (Req 8.8)."""
        if self._sim is None:
            self._console.print(
                "[bold red]✗[/bold red] SelfImprovementModule tidak tersedia."
            )
            return

        self._console.print("Menjalankan rollback ke versi konfigurasi sebelumnya...")
        try:
            await self._sim.rollback()
            self._console.print(
                "[bold green]✓[/bold green] Rollback berhasil. "
                "Konfigurasi telah dipulihkan ke versi backup terakhir."
            )
        except FileNotFoundError:
            self._console.print(
                "[bold red]✗[/bold red] Tidak ada backup yang tersedia untuk rollback."
            )
        except Exception as exc:
            self._console.print(f"[bold red]✗[/bold red] Rollback gagal: {exc}")

    async def _process_autonomous(self, goal: str) -> None:
        """Jalankan agent dalam mode otonom penuh (closed-loop)."""
        self._console.print(
            Panel(
                f"[bold]{goal}[/bold]",
                title="[bold green]Autonomous Mode[/bold green]",
                subtitle="Agent akan loop sampai goal tercapai atau budget habis",
                border_style="green",
            )
        )

        collected: list[str] = []
        try:
            async for token in self._agent.process_autonomous(goal):
                collected.append(token)
                self._console.print(token, end="", highlight=False)
        except KeyboardInterrupt:
            self._console.print("\n[yellow]Autonomous mode dihentikan oleh pengguna.[/yellow]")
        except Exception as exc:
            self._console.print(f"\n[bold red]Error: {exc}[/bold red]")
        finally:
            if collected:
                self._console.print()

    def _show_memory(self) -> None:
        """Tampilkan status memori agent."""
        memory = self._agent._memory
        working = memory.get_all_working()
        task_hist = memory.get_task_history(limit=5)
        self_knowledge = memory.get_self_knowledge("tool_failure_patterns", {})
        strategies = memory.get_self_knowledge("successful_strategies", [])

        table = Table(title="Agent Memory", show_header=True, header_style="bold cyan")
        table.add_column("Layer", style="bold")
        table.add_column("Status")

        table.add_row("Working Memory", f"{len(working)} entries" if working else "Kosong")
        table.add_row("Task History", f"{len(task_hist)} langkah terakhir")
        table.add_row("Tool Failures", f"{len(self_knowledge)} tools bermasalah")
        table.add_row("Strategies", f"{len(strategies)} strategi tersimpan")

        self._console.print(table)

    async def _show_debug(self) -> None:
        """Tampilkan laporan kesehatan sistem."""
        from agent.self_improvement.self_debugging import SelfDebuggingModule
        debug = SelfDebuggingModule(
            registry=self._registry,
            memory_system=self._agent._memory,
        )
        report = debug.analyze_system_health()

        self._console.print(Panel(
            "\n".join(report.identified_weaknesses),
            title="[bold yellow]System Health Report[/bold yellow]",
            border_style="yellow",
        ))

    async def _do_stop(self, graceful: bool = True) -> None:
        """Hentikan Agent dan tandai CLI sebagai tidak berjalan (Req 1.7, 1.8)."""
        self._running = False
        if graceful:
            self._console.print(
                "\n[bold yellow]Menghentikan Agent...[/bold yellow]"
            )
        try:
            await asyncio.wait_for(self._agent.stop(), timeout=3.0)
        except asyncio.TimeoutError:
            pass  # Tetap keluar meski stop() melebihi 3 detik
        if graceful:
            self._console.print("[bold green]Sesi diakhiri.[/bold green]")

    async def _process_instruction(self, instruction: str) -> None:
        """Kirim instruksi ke Agent, tampilkan spinner, dan render respons.

        Spinner dijalankan sebagai task asyncio yang terpisah agar tetap
        diperbarui setiap 200ms (Req 1.3) selama Agent memproses.

        Respons di-stream token demi token (Req 1.2). Setelah seluruh token
        diterima, blok kode ditampilkan ulang dengan syntax highlighting.
        """
        # Kumpulkan token dalam queue agar streaming dan spinner bisa berjalan
        # bersama tanpa blocking.
        token_queue: asyncio.Queue[str | None] = asyncio.Queue()

        async def _produce() -> None:
            """Hasilkan token dari Agent dan masukkan ke queue."""
            try:
                async for token in self._agent.process(instruction):
                    await token_queue.put(token)
            finally:
                await token_queue.put(None)  # sentinel

        # Tampilkan spinner menggunakan Rich Live (diperbarui otomatis)
        spinner = Spinner(_SPINNER_NAME, text="Sedang memproses...")
        collected: list[str] = []
        first_token_received = False

        # Mulai produsen token sebagai background task
        produce_task = asyncio.create_task(_produce())

        with Live(
            spinner,
            console=self._console,
            refresh_per_second=int(1000 / SPINNER_INTERVAL_MS),  # 5 fps
            transient=True,
        ) as live:
            while True:
                try:
                    token = await asyncio.wait_for(
                        token_queue.get(), timeout=0.5
                    )
                except asyncio.TimeoutError:
                    # Tidak ada token dalam 500ms — spinner tetap berjalan
                    continue

                if token is None:
                    break

                if not first_token_received:
                    # Hentikan Live (spinner) saat token pertama tiba
                    live.stop()
                    first_token_received = True

                # Cetak token langsung ke konsol (Req 1.2)
                self._console.print(token, end="", highlight=False)
                collected.append(token)

        # Tunggu task produsen selesai
        await produce_task

        # Pastikan ada newline di akhir
        if collected:
            self._console.print()

        full_text = "".join(collected)

        # Post-processing: render ulang teks lengkap dengan syntax highlighting
        # untuk blok kode (Req 1.10, 1.11). Hanya jika ada blok kode.
        if "```" in full_text:
            self._console.print()
            self._render_highlighted_response(full_text)

    def _render_code_blocks(self, text: str) -> None:
        """Render blok kode dalam teks dengan syntax highlighting.

        Dipanggil setelah streaming selesai untuk memperkaya tampilan.
        Tidak menampilkan ulang teks non-kode (sudah dicetak saat streaming).

        Args:
            text: Teks lengkap yang mungkin mengandung blok kode Markdown.
        """
        for match in _CODE_BLOCK_PATTERN.finditer(text):
            lang = match.group("lang").strip() or "text"
            code = match.group("code")
            if lang.lower() in ("", "text", "plaintext"):
                # Req 1.11: blok kode tanpa bahasa — format teks biasa
                self._console.print(
                    Panel(
                        code.rstrip(),
                        border_style="dim",
                        title="[dim]kode[/dim]",
                        title_align="left",
                    )
                )
            else:
                # Req 1.10: blok kode dengan bahasa → syntax highlighting
                syntax = Syntax(
                    code.rstrip(),
                    lang,
                    theme="monokai",
                    word_wrap=True,
                    line_numbers=False,
                )
                self._console.print(syntax)

    def _render_highlighted_response(self, text: str) -> None:
        """Render seluruh respons dengan syntax highlighting pada blok kode.

        Memisahkan teks narasi dan blok kode, lalu merender masing-masing
        dengan gaya yang sesuai. Digunakan sebagai tampilan "versi akhir"
        setelah streaming selesai.

        Args:
            text: Teks lengkap respons Agent.
        """
        self._console.print(
            Panel(
                "[dim]Respons lengkap dengan highlighting:[/dim]",
                border_style="dim cyan",
                expand=False,
            )
        )

        last_end = 0
        for match in _CODE_BLOCK_PATTERN.finditer(text):
            # Narasi sebelum blok kode
            narasi = text[last_end : match.start()].strip()
            if narasi:
                self._console.print(Markdown(narasi))

            lang = match.group("lang").strip() or "text"
            code = match.group("code").rstrip()

            if lang.lower() in ("", "text", "plaintext"):
                # Req 1.11: blok tanpa bahasa
                self._console.print(
                    Panel(code, border_style="dim", title="[dim]kode[/dim]", title_align="left")
                )
            else:
                # Req 1.10: blok dengan bahasa
                syntax = Syntax(code, lang, theme="monokai", word_wrap=True)
                self._console.print(syntax)

            last_end = match.end()

        # Narasi setelah blok kode terakhir
        trailing = text[last_end:].strip()
        if trailing:
            self._console.print(Markdown(trailing))


__all__ = [
    "MAX_INPUT_LENGTH",
    "CLIConfig",
    "CLI",
]
