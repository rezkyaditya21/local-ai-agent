"""
agent/core/orchestrator.py

Agent Orchestrator — pusat kendali yang menghubungkan semua subsistem:
ModelManager, Executor, ConfirmationGate, AuditLogger, dan Blocklist.

Alur utama:
1. Terima instruksi dari CLI.
2. Kirim ke ModelManager untuk mendapatkan respons/rencana tindakan (tool calls).
3. Parsing tool calls dari output model (format JSON block).
4. Eksekusi tool calls via Executor melalui _execute_plan().
5. Jika ada hasil tool, kirim kembali ke model untuk sintesis.
6. Stream token respons akhir ke pemanggil.
7. Catat InteractionRecord ke riwayat sesi.

Keamanan:
- Setiap tindakan dicatat ke AuditLogger dengan timestamp ISO 8601.
- Operasi berisiko tinggi selalu melewati ConfirmationGate.
- Setelah 10 tindakan berurutan tanpa input pengguna, Agent berhenti dan
  meminta konfirmasi untuk melanjutkan (Requirement 10.9).
- /stop atau Ctrl+C menghentikan semua operasi dalam ≤3 detik.

Requirements: 1.2, 1.7, 1.9, 10.3, 10.9
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, AsyncIterator

from agent.core.audit_logger import AuditLogger
from agent.core.blocklist import Blocklist
from agent.core.confirmation_gate import ConfirmationGate, ConfirmationRequest
from agent.core.planner import MultiStepPlanner
from agent.core.system_inspector import SystemInspector
from agent.memory.memory_system import MemorySystem
from agent.models.schemas import InteractionRecord, TaskPlan, ToolCall, ToolResult

if TYPE_CHECKING:
    from agent.core.executor import Executor
    from agent.models.manager import ModelManager

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Konstanta
# ---------------------------------------------------------------------------

MAX_CONSECUTIVE_ACTIONS: int = 10

# Regex tidak dapat menangani nested braces secara andal — gunakan pendekatan
# JSON scanner yang mencari objek JSON di dalam teks secara iteratif.


# ---------------------------------------------------------------------------
# Helper: timestamp
# ---------------------------------------------------------------------------

def _utc_now_iso() -> str:
    """Kembalikan timestamp UTC saat ini dalam format ISO 8601."""
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


# ---------------------------------------------------------------------------
# Helper: parse tool calls dari output model
# ---------------------------------------------------------------------------

def _extract_json_objects(text: str) -> list[str]:
    """Ekstrak semua JSON object top-level dari teks secara iteratif.

    Menggunakan pendekatan brace-counting agar mendukung nested objects
    (mis. ``"params": {"key": "value"}``).

    Args:
        text: Teks arbitrer yang mungkin mengandung JSON objects.

    Returns:
        Daftar string JSON object yang valid (parseable).
    """
    objects: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        if text[i] != "{":
            i += 1
            continue
        # Temukan akhir object dengan menghitung kedalaman brace
        depth = 0
        in_string = False
        escape_next = False
        j = i
        while j < n:
            ch = text[j]
            if escape_next:
                escape_next = False
            elif ch == "\\":
                escape_next = True
            elif ch == '"' and not escape_next:
                in_string = not in_string
            elif not in_string:
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        objects.append(text[i : j + 1])
                        i = j + 1
                        break
            j += 1
        else:
            break
    return objects


_TOOL_NAME_ALIASES: dict[str, str] = {
    "websearchtool": "web_search",
    "websearch": "web_search",
    "filesystemtool": "filesystem",
    "shelltool": "shell",
    "codesearchtool": "code_search",
    "codesearch": "code_search",
    "gittool": "git",
    "testrunnertool": "test_runner",
    "testrunner": "test_runner",
    "pythonexectool": "python_exec",
    "pythonexec": "python_exec",
    "systeminspecttool": "system_inspect",
    "systeminspect": "system_inspect",
    "projectinspecttool": "project_inspect",
    "projectinspect": "project_inspect",
    "benchmarktool": "benchmark",
    "databasetool": "database",
    "browsertool": "browser",
    "httpapitool": "http_api",
}


def _parse_tool_calls(text: str) -> list[ToolCall]:
    """Cari dan parse semua JSON tool call block dari teks output model.

    Format yang dikenali::

        {"tool": "filesystem", "params": {"path": "/tmp/test.txt"}}
        {"tool_name": "shell", "params": {"command": "ls -la"}}

    Args:
        text: Teks output dari model, mungkin mengandung narasi dan JSON block.

    Returns:
        Daftar :class:`~agent.models.schemas.ToolCall` yang ditemukan,
        urutan sesuai kemunculan dalam teks.
    """
    calls: list[ToolCall] = []
    for raw in _extract_json_objects(text):
        try:
            data: dict = json.loads(raw)
        except json.JSONDecodeError:
            continue

        if not isinstance(data, dict):
            continue

        # Dukung kedua bentuk kunci: "tool" dan "tool_name"
        tool_name: str = data.get("tool") or data.get("tool_name") or ""
        params: dict = data.get("params", {})

        if not tool_name:
            continue

        tool_name = tool_name.strip()
        normalized_name = _TOOL_NAME_ALIASES.get(tool_name.lower(), tool_name)

        calls.append(
            ToolCall(
                tool_name=normalized_name,
                params=params if isinstance(params, dict) else {},
            )
        )
    return calls


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


class Agent:
    """Orkestrator utama yang menghubungkan semua subsistem Agent.

    Args:
        model_manager: :class:`~agent.models.manager.ModelManager` untuk
            menghasilkan respons dan streaming token.
        executor: :class:`~agent.core.executor.Executor` untuk menjalankan
            tool calls.
        confirmation_gate: :class:`~agent.core.confirmation_gate.ConfirmationGate`
            untuk konfirmasi operasi berisiko tinggi.
        audit_logger: :class:`~agent.core.audit_logger.AuditLogger` untuk
            pencatatan semua tindakan.
        blocklist: :class:`~agent.core.blocklist.Blocklist` untuk memeriksa
            apakah operasi terblokir.
    """

    def __init__(
        self,
        model_manager: "ModelManager",
        executor: "Executor",
        confirmation_gate: ConfirmationGate,
        audit_logger: AuditLogger,
        blocklist: Blocklist,
        memory_system: MemorySystem | None = None,
        planner: MultiStepPlanner | None = None,
        system_inspector: SystemInspector | None = None,
    ) -> None:
        self._model_manager = model_manager
        self._executor = executor
        self._confirmation_gate = confirmation_gate
        self._audit_logger = audit_logger
        self._blocklist = blocklist
        self._memory = memory_system or MemorySystem()
        self._planner = planner or MultiStepPlanner()
        self._system_inspector = system_inspector or SystemInspector()

        from agent.core.controller import AgentController
        self.controller = AgentController(
            model_manager=model_manager,
            executor=executor,
            registry=getattr(executor, "_registry", None),
            audit_logger=audit_logger,
            memory_system=self._memory,
            planner=self._planner,
        )

        # Riwayat sesi: oldest → newest
        self._history: list[InteractionRecord] = []

        # Event untuk sinyal stop
        self._stop_event: asyncio.Event = asyncio.Event()

        # Task yang sedang berjalan (untuk cancel pada stop())
        self._active_tasks: set[asyncio.Task] = set()

    async def process_autonomous(self, goal: str, budget: Any = None) -> AsyncIterator[str]:
        """Proses tugas otonom closed-loop melalui AgentController."""
        async for token in self.controller.execute_task(goal, budget=budget):
            yield token

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def process(self, instruction: str) -> AsyncIterator[str]:
        """Proses instruksi dan stream token respons.

        Alur:
        1. Reset stop event (pemanggil baru = operasi baru).
        2. Stream respons pertama dari model (mungkin mengandung tool calls).
        3. Parse tool calls dari output model.
        4. Eksekusi tool calls via ``_execute_plan()``.
        5. Jika ada hasil tool, kirim kembali ke model untuk sintesis akhir.
        6. Catat :class:`~agent.models.schemas.InteractionRecord` ke riwayat.
        7. Yield semua token ke pemanggil.

        Args:
            instruction: Instruksi teks dari pengguna (≤32.000 karakter).

        Yields:
            Token string satu per satu.

        Note:
            Pemanggil bertanggung jawab untuk tidak memanggil ``process()``
            setelah ``stop()`` dipanggil. Pemeriksaan ``_stop_event`` dilakukan
            di setiap tahap utama untuk early exit.
        """
        self._stop_event.clear()
        collected_first_pass: list[str] = []
        collected_final: list[str] = []
        tool_calls_executed: list[ToolCall] = []
        tool_results: list[ToolResult] = []

        # ----------------------------------------------------------------
        # Tahap 1: Dapatkan respons awal dari model
        # ----------------------------------------------------------------
        try:
            async for token in self._model_manager.generate(
                prompt=instruction,
                history=self._history,
            ):
                if self._stop_event.is_set():
                    break
                collected_first_pass.append(token)
                yield token
        except Exception as exc:  # noqa: BLE001
            err_msg = f"[Error model: {exc}]"
            _logger.error("Error saat generate respons: %s", exc)
            self._audit_logger.log_error(
                error=str(exc),
                context={"instruction": instruction, "phase": "generate_first_pass"},
            )
            yield err_msg
            self._history.append(
                InteractionRecord(
                    instruction=instruction,
                    response=err_msg,
                    tool_calls=[],
                    timestamp=_utc_now_iso(),
                )
            )
            return

        if self._stop_event.is_set():
            return

        first_pass_text = "".join(collected_first_pass)

        # ----------------------------------------------------------------
        # Tahap 2: Parse dan eksekusi tool calls (jika ada)
        # ----------------------------------------------------------------
        tool_calls = _parse_tool_calls(first_pass_text)

        if tool_calls:
            plan = TaskPlan(
                original_instruction=instruction,
                steps=tool_calls,
                reasoning="Parsed from model output",
            )
            try:
                tool_results = await self._execute_plan(plan)
            except Exception as exc:  # noqa: BLE001
                _logger.error("Error saat _execute_plan: %s", exc)
                self._audit_logger.log_error(
                    error=str(exc),
                    context={"instruction": instruction, "phase": "execute_plan"},
                )
            tool_calls_executed = tool_calls

        if self._stop_event.is_set():
            return

        # ----------------------------------------------------------------
        # Tahap 3: Sintesis respons akhir jika ada hasil tool
        # ----------------------------------------------------------------
        if tool_results:
            synthesis_prompt = self._build_synthesis_prompt(
                instruction=instruction,
                first_pass=first_pass_text,
                tool_results=tool_results,
            )
            try:
                async for token in self._model_manager.generate(
                    prompt=synthesis_prompt,
                    history=self._history,
                ):
                    if self._stop_event.is_set():
                        break
                    collected_final.append(token)
                    yield token
            except Exception as exc:  # noqa: BLE001
                err_msg = f"[Error sintesis: {exc}]"
                _logger.error("Error saat sintesis: %s", exc)
                self._audit_logger.log_error(
                    error=str(exc),
                    context={"instruction": instruction, "phase": "synthesis"},
                )
                yield err_msg
                collected_final.append(err_msg)
        else:
            # Tidak ada tool calls — first_pass sudah merupakan respons akhir
            collected_final = collected_first_pass

        # ----------------------------------------------------------------
        # Tahap 4: Catat ke riwayat sesi
        # ----------------------------------------------------------------
        final_response = "".join(collected_final)
        self._history.append(
            InteractionRecord(
                instruction=instruction,
                response=final_response,
                tool_calls=tool_calls_executed,
                timestamp=_utc_now_iso(),
            )
        )
        self._audit_logger.log_action(
            action="agent.process",
            params={"instruction": instruction[:200]},
            result=f"success, {len(tool_calls_executed)} tool_calls",
            confirmed=True,
        )

    async def stop(self) -> None:
        """Hentikan semua operasi Agent dalam ≤3 detik.

        Menyetel ``_stop_event`` sehingga semua loop yang memeriksa event
        ini akan berhenti. Juga membatalkan semua :class:`asyncio.Task`
        aktif yang terdaftar di ``_active_tasks``.

        Setelah memanggil ``stop()``, pemanggil HARUS membuat instansi Agent
        baru atau memanggil ``_stop_event.clear()`` sebelum menggunakan
        ``process()`` kembali — namun ini ditangani oleh ``process()`` itu
        sendiri pada setiap pemanggilan baru.
        """
        self._stop_event.set()

        # Batalkan semua task aktif
        tasks_to_cancel = list(self._active_tasks)
        for task in tasks_to_cancel:
            if not task.done():
                task.cancel()

        # Tunggu hingga semua task selesai (dibatalkan), maksimum 3 detik
        if tasks_to_cancel:
            await asyncio.wait(
                tasks_to_cancel,
                timeout=3.0,
                return_when=asyncio.ALL_COMPLETED,
            )

        self._active_tasks.clear()
        _logger.info("Agent dihentikan.")

    def get_history(self) -> list[InteractionRecord]:
        """Kembalikan riwayat interaksi sesi aktif dari terlama ke terbaru.

        Returns:
            Salinan daftar :class:`~agent.models.schemas.InteractionRecord`,
            diurutkan dari yang paling lama (indeks 0) ke yang paling baru.
        """
        return list(self._history)

    # ------------------------------------------------------------------
    # Internal: _execute_plan
    # ------------------------------------------------------------------

    async def _execute_plan(self, plan: TaskPlan) -> list[ToolResult]:
        """Eksekusi setiap tool call dalam rencana secara berurutan.

        Aturan keamanan:
        - Setelah ``MAX_CONSECUTIVE_ACTIONS`` (10) tindakan berurutan tanpa
          input pengguna, Agent berhenti dan meminta konfirmasi untuk melanjutkan
          (Requirement 10.9). Jika pengguna menolak, eksekusi dihentikan.
        - Setiap tindakan dicatat ke AuditLogger.
        - Stop event diperiksa sebelum setiap tindakan.

        Args:
            plan: :class:`~agent.models.schemas.TaskPlan` yang berisi daftar
                tool calls yang akan dieksekusi.

        Returns:
            Daftar :class:`~agent.models.schemas.ToolResult`, satu per tool call
            yang dieksekusi. Tool calls yang tidak dieksekusi (karena stop atau
            penolakan konfirmasi) tidak disertakan.
        """
        results: list[ToolResult] = []
        consecutive_count: int = 0

        for call in plan.steps:
            if self._stop_event.is_set():
                _logger.info("_execute_plan: stop event terdeteksi, berhenti.")
                break

            # ---- Pemeriksaan batas 10 tindakan berurutan ----
            if consecutive_count >= MAX_CONSECUTIVE_ACTIONS:
                _logger.info(
                    "_execute_plan: mencapai batas %d tindakan berurutan, "
                    "meminta konfirmasi.",
                    MAX_CONSECUTIVE_ACTIONS,
                )
                proceed = await self._confirmation_gate.request(
                    ConfirmationRequest(
                        operation_type="consecutive_action_limit",
                        description=(
                            f"Agent telah menjalankan {consecutive_count} tindakan berurutan "
                            f"tanpa input pengguna. Lanjutkan eksekusi?"
                        ),
                    )
                )
                self._audit_logger.log_action(
                    action="agent.consecutive_limit_check",
                    params={"consecutive_count": consecutive_count},
                    result="confirmed" if proceed else "cancelled",
                    confirmed=proceed,
                )
                if not proceed:
                    _logger.info(
                        "_execute_plan: pengguna menolak melanjutkan, eksekusi dihentikan."
                    )
                    break
                # Reset counter setelah konfirmasi
                consecutive_count = 0

            # ---- Eksekusi tool call ----
            _logger.debug(
                "_execute_plan: mengeksekusi '%s' dengan params %s",
                call.tool_name,
                call.params,
            )
            self._audit_logger.log_action(
                action=f"tool.{call.tool_name}",
                params=call.params,
                result="pending",
                confirmed=True,
            )

            try:
                result: ToolResult = await self._executor.execute(call)
            except Exception as exc:  # noqa: BLE001
                # Tangkap semua exception — isolasi error agar sesi tidak berhenti
                error_msg = f"[{type(exc).__name__}] {exc}"
                _logger.error(
                    "Unhandled exception dari executor untuk tool '%s': %s",
                    call.tool_name,
                    exc,
                )
                self._audit_logger.log_error(
                    error=error_msg,
                    context={
                        "tool_name": call.tool_name,
                        "params": call.params,
                        "phase": "executor.execute",
                    },
                )
                result = ToolResult(
                    success=False,
                    data=None,
                    error=error_msg,
                    tool_name=call.tool_name,
                )

            # Catat hasil ke audit log
            result_summary = "success" if result.success else f"failed: {result.error}"
            self._audit_logger.log_action(
                action=f"tool.{call.tool_name}",
                params=call.params,
                result=result_summary,
                confirmed=True,
            )

            results.append(result)
            consecutive_count += 1

        return results

    # ------------------------------------------------------------------
    # Internal: _build_synthesis_prompt
    # ------------------------------------------------------------------

    def _build_synthesis_prompt(
        self,
        instruction: str,
        first_pass: str,
        tool_results: list[ToolResult],
    ) -> str:
        """Bangun prompt sintesis yang menyertakan hasil tool calls.

        Format prompt::

            Instruksi pengguna: <instruction>

            Hasil tool yang dijalankan:
            Tool 1 (<name>): success/failed
            Data: <data>

            Berdasarkan hasil di atas, berikan respons akhir untuk pengguna.

        Args:
            instruction: Instruksi awal dari pengguna.
            first_pass: Respons awal model (termasuk tool call JSON blocks).
            tool_results: Daftar hasil eksekusi tool.

        Returns:
            String prompt yang siap dikirim ke model.
        """
        lines: list[str] = [
            f"Instruksi pengguna: {instruction}",
            "",
            "Hasil tool yang dijalankan:",
        ]
        for i, result in enumerate(tool_results, start=1):
            status = "berhasil" if result.success else f"gagal: {result.error}"
            lines.append(f"Tool {i} ({result.tool_name}): {status}")
            if result.data is not None:
                # Batasi output data agar prompt tidak terlalu panjang
                data_str = str(result.data)
                if len(data_str) > 2000:
                    data_str = data_str[:2000] + "... [dipotong]"
                lines.append(f"Data: {data_str}")

        lines.extend([
            "",
            "Berdasarkan hasil di atas, sampaikan RINGKASAN FAKTA DAN ISI INFORMASI secara SINGKAT, RINGKAS, dan LANGSUNG KE POIN PENTING (2-4 poin fakta). JANGAN hanya menyebutkan nama situs web/domain, melainkan jelaskan fakta atau isi informasi dari hasil pencarian tersebut.",
        ])
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Exports
# ---------------------------------------------------------------------------

__all__ = [
    "Agent",
    "MAX_CONSECUTIVE_ACTIONS",
]
