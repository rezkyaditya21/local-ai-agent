"""
agent/core/orchestrator.py

Agent Orchestrator — pusat kendali yang menghubungkan semua subsistem:
ModelManager, Executor, ConfirmationGate, AuditLogger, dan Blocklist.

Dua mode eksekusi:
1. process() — single-iteration (backward compat, digunakan CLI untuk chat biasa)
2. process_autonomous() — closed-loop autonomous (digunakan untuk tugas engineering)

Keduanya delegate ke AgentController sebagai pusat execution utama.

Keamanan:
- Setiap tindakan dicatat ke AuditLogger dengan timestamp ISO 8601.
- Operasi berisiko tinggi selalu melewati ConfirmationGate.
- /stop atau Ctrl+C menghentikan semua operasi dalam <= 3 detik.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, AsyncIterator

from agent.core.audit_logger import AuditLogger
from agent.core.budget import ExecutionBudget
from agent.core.blocklist import Blocklist
from agent.core.confirmation_gate import ConfirmationGate, ConfirmationRequest
from agent.core.controller import AgentController
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


# ---------------------------------------------------------------------------
# Helper: timestamp
# ---------------------------------------------------------------------------

def _utc_now_iso() -> str:
    """Kembalikan timestamp UTC saat ini dalam format ISO 8601."""
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


class Agent:
    """Orkestrator utama yang menghubungkan semua subsistem Agent.

    Dua mode eksekusi utama:
    - process(): single-iteration (backward compat)
    - process_autonomous(): closed-loop via AgentController

    Keduanya mengarah ke AgentController sebagai pusat execution.

    Args:
        model_manager: ModelManager untuk generate.
        executor: Executor untuk menjalankan tool calls.
        confirmation_gate: ConfirmationGate untuk operasi berisiko.
        audit_logger: AuditLogger untuk pencatatan.
        blocklist: Blocklist untuk filtering.
        memory_system: MemorySystem (opsional).
        planner: MultiStepPlanner (opsional).
        system_inspector: SystemInspector (opsional).
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
        budget: ExecutionBudget | None = None,
    ) -> None:
        self._model_manager = model_manager
        self._executor = executor
        self._confirmation_gate = confirmation_gate
        self._audit_logger = audit_logger
        self._blocklist = blocklist
        self._memory = memory_system or MemorySystem()
        self._planner = planner or MultiStepPlanner()
        self._system_inspector = system_inspector or SystemInspector()
        self._budget = budget

        # Build AgentController — pusat execution
        self.controller = AgentController(
            model_manager=model_manager,
            executor=executor,
            registry=getattr(executor, "_registry", None),
            audit_logger=audit_logger,
            memory_system=self._memory,
            planner=self._planner,
        )

        # Riwayat sesi: oldest -> newest
        self._history: list[InteractionRecord] = []

        # Event untuk sinyal stop
        self._stop_event: asyncio.Event = asyncio.Event()

        # Task yang sedang berjalan (untuk cancel pada stop())
        self._active_tasks: set[asyncio.Task] = set()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def process_autonomous(self, goal: str, budget: ExecutionBudget | None = None) -> AsyncIterator[str]:
        """Proses tugas otonom closed-loop melalui AgentController.

        Ini adalah mode utama untuk tugas engineering yang kompleks.
        Agent akan loop OBSERVE -> PLAN -> ACT -> EVALUATE -> REPEAT
        sampai goal tercapai atau budget habis.
        """
        effective_budget = budget or self._budget or ExecutionBudget()
        async for token in self.controller.execute_task(goal, budget=effective_budget):
            yield token

    async def process(self, instruction: str) -> AsyncIterator[str]:
        """Proses instruksi pengguna — otomatis mengeksekusi tool (terminal, internet,
        filesystem, dsb.) jika diperlukan dan mengembalikan respons lengkap.
        """
        self._stop_event.clear()

        tool_catalog = self._executor._registry.format_catalog() if hasattr(self._executor, "_registry") else ""
        from agent.core.prompting import build_chat_prompt, summarize_tool_results
        from agent.core.controller import _parse_tool_calls

        current_prompt = build_chat_prompt(
            instruction=instruction,
            tool_catalog=tool_catalog,
        )

        all_collected_tokens: list[str] = []
        executed_tool_calls: list[ToolCall] = []
        max_turns = 5

        for turn in range(max_turns):
            if self._stop_event.is_set():
                break

            turn_tokens: list[str] = []
            try:
                async for token in self._model_manager.generate(prompt=current_prompt, history=[]):
                    if self._stop_event.is_set():
                        break
                    turn_tokens.append(token)
                    all_collected_tokens.append(token)
                    yield token
            except Exception as exc:
                err_msg = f"\n[Error: {exc}]\n"
                all_collected_tokens.append(err_msg)
                yield err_msg
                _logger.warning("Model generate error: %s", exc)
                break

            turn_text = "".join(turn_tokens)
            tool_calls = _parse_tool_calls(turn_text)

            if not tool_calls:
                # Tidak ada tool calls lebih lanjut — respons sudah selesai
                break

            # Eksekusi tool calls
            turn_results: list[ToolResult] = []
            for tc in tool_calls:
                if self._stop_event.is_set():
                    break
                executed_tool_calls.append(tc)
                yield f"\n[Menjalankan tool '{tc.tool_name}']...\n"
                try:
                    result = await self._executor.execute(tc)
                    turn_results.append(result)
                    if result.success and result.data is not None:
                        # Tampilkan output singkat jika berupa stdout atau ringkasan
                        if isinstance(result.data, dict) and "stdout" in result.data:
                            stdout = result.data.get("stdout", "").strip()
                            if stdout:
                                yield f"{stdout}\n"
                except Exception as exc:
                    turn_results.append(ToolResult(success=False, data=None, error=str(exc), tool_name=tc.tool_name))

            # Bangun prompt follow-up dengan hasil eksekusi tool
            tool_summary = summarize_tool_results(turn_results)
            current_prompt = (
                f"{build_chat_prompt(instruction=instruction, tool_catalog=tool_catalog)}\n\n"
                f"Hasil eksekusi tool:\n{tool_summary}\n\n"
                "Gunakan hasil eksekusi tool di atas untuk memberikan jawaban yang jelas, akurat, dan lengkap kepada pengguna. "
                "Jika sudah terjawab, jawab langsung dengan teks biasa tanpa JSON tool."
            )

        # Record interaction
        final_response = "".join(all_collected_tokens)
        self._history.append(
            InteractionRecord(
                instruction=instruction,
                response=final_response,
                tool_calls=executed_tool_calls,
                timestamp=_utc_now_iso(),
            )
        )
        self._audit_logger.log_action(
            action="agent.process",
            params={"instruction": instruction[:200]},
            result=f"completed, {len(all_collected_tokens)} tokens, {len(executed_tool_calls)} tool_calls",
            confirmed=True,
        )

    async def stop(self) -> None:
        """Hentikan semua operasi Agent dalam <= 3 detik."""
        self._stop_event.set()

        # Batalkan semua task aktif
        tasks_to_cancel = list(self._active_tasks)
        for task in tasks_to_cancel:
            if not task.done():
                task.cancel()

        if tasks_to_cancel:
            await asyncio.wait(
                tasks_to_cancel,
                timeout=3.0,
                return_when=asyncio.ALL_COMPLETED,
            )

        self._active_tasks.clear()
        _logger.info("Agent dihentikan.")

    def get_history(self) -> list[InteractionRecord]:
        """Kembalikan riwayat interaksi sesi aktif."""
        return list(self._history)

    def set_budget(self, budget: ExecutionBudget) -> None:
        """Atur budget untuk autonomous execution."""
        self._budget = budget


# ---------------------------------------------------------------------------
# Exports
# ---------------------------------------------------------------------------

__all__ = [
    "Agent",
    "MAX_CONSECUTIVE_ACTIONS",
]
