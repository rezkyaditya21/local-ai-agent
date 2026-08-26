"""
agent/core/controller.py

Agent Controller — pusat orchestration untuk closed-loop autonomous execution.

Komponen utama:
- `TaskState`: State komprehensif dari sebuah tugas sepanjang iterasi.
- `AgentController`: Pengendali closed-loop execution loop.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, AsyncIterator

from agent.core.audit_logger import AuditLogger
from agent.core.budget import ExecutionBudget
from agent.core.capabilities import CapabilityManager, CapabilityMap
from agent.core.evaluator import ObjectiveEvaluator, VerificationResult
from agent.core.model_router import ModelRouter
from agent.core.planner import ExecutionPlan, MultiStepPlanner, SubTask
from agent.memory.memory_system import MemorySystem
from agent.models.schemas import ToolCall, ToolResult
from agent.self_improvement.checkpoint import CheckpointManager
from agent.tools.registry import ToolRegistry

if TYPE_CHECKING:
    from agent.core.executor import Executor
    from agent.models.manager import ModelManager

_logger = logging.getLogger(__name__)


@dataclass
class TaskState:
    """State tugas otonom yang dipertahankan sepanjang iterasi."""

    goal: str
    iteration: int = 0
    status: str = "in_progress"  # "in_progress" | "completed" | "failed" | "exhausted"
    plan: ExecutionPlan | None = None
    last_results: list[ToolResult] = field(default_factory=list)
    last_eval: VerificationResult | None = None
    execution_logs: list[str] = field(default_factory=list)


class AgentController:
    """Agent Controller sentral untuk mengkoordinasikan seluruh subsistem dalam closed-loop execution."""

    def __init__(
        self,
        model_manager: "ModelManager",
        executor: "Executor",
        registry: ToolRegistry,
        audit_logger: AuditLogger,
        memory_system: MemorySystem | None = None,
        planner: MultiStepPlanner | None = None,
        evaluator: ObjectiveEvaluator | None = None,
        capability_mgr: CapabilityManager | None = None,
        model_router: ModelRouter | None = None,
        checkpoint_mgr: CheckpointManager | None = None,
    ) -> None:
        self._model_manager = model_manager
        self._executor = executor
        self._registry = registry
        self._audit_logger = audit_logger

        self.memory = memory_system or MemorySystem()
        self.planner = planner or MultiStepPlanner()
        self.evaluator = evaluator or ObjectiveEvaluator()
        self.capability_mgr = capability_mgr or CapabilityManager()
        self.model_router = model_router or ModelRouter(model_manager)
        self.checkpoint_mgr = checkpoint_mgr or CheckpointManager()

    async def execute_task(
        self,
        goal: str,
        budget: ExecutionBudget | None = None,
    ) -> AsyncIterator[str]:
        """Jalankan Closed-Loop Autonomous Loop:
        OBSERVE → ANALYZE → PLAN → ACT → OBSERVE RESULT → EVALUATE → REPLAN/VERIFY → REPEAT.

        Args:
            goal: Tujuan utama dari pengguna.
            budget: Anggaran eksekusi opsional.

        Yields:
            Token string streaming untuk pemanggil.
        """
        budget = budget or ExecutionBudget()
        cap_map = self.capability_mgr.detect_capabilities()
        state = TaskState(goal=goal)

        yield f"🚀 [AgentController] Memulai tugas otonom: '{goal}'\n"
        yield f"📌 [Capabilities] {cap_map.os_platform} | Python {cap_map.python_version} | Tools: {len(self._registry.list_all())}\n\n"

        while True:
            # 1. Periksa batas anggaran eksekusi
            is_exhausted, reason = budget.is_exhausted()
            if is_exhausted:
                state.status = "exhausted"
                yield f"\n⚠️ [Budget Exhausted] {reason}\n"
                yield f"📊 {budget.remaining_summary()}\n"
                break

            budget.consume_iteration()
            state.iteration = budget.current_iteration

            yield f"--- [Iterasi {state.iteration}/{budget.max_iterations}] ---\n"

            # 2. OBSERVE & ANALYZE: Pilih model terbaik & generate rencana/tindakan
            model_name = self.model_router.select_model_for_task("reasoning" if state.iteration == 1 else "coding")

            # 3. PLAN & ACT: Kirim instruksi + state ke model
            prompt_context = f"Goal: {goal}\nIterasi: {state.iteration}\nBudget: {budget.remaining_summary()}"
            if state.last_eval and not state.last_eval.is_verified:
                prompt_context += f"\nWarning Evaluasi Sebelumnya (GAGAL): {', '.join(state.last_eval.failure_reasons)}"

            collected_tokens = []
            try:
                async for token in self._model_manager.generate(prompt=prompt_context, history=[]):
                    collected_tokens.append(token)
                    yield token
            except Exception as exc:
                yield f"\n[Error Model: {exc}]\n"
                break

            response_text = "".join(collected_tokens)
            from agent.core.orchestrator import _parse_tool_calls
            tool_calls = _parse_tool_calls(response_text)

            if not tool_calls:
                # Tidak ada tool call lagi — anggap model telah menyelesaikan jawaban
                state.status = "completed"
                yield "\n✅ [AgentController] Eksekusi selesai tanpa tool call tambahan.\n"
                break

            # 4. ACT: Eksekusi tool calls
            from agent.models.schemas import TaskPlan
            plan = TaskPlan(original_instruction=goal, steps=tool_calls, reasoning="Closed-loop step")

            tool_results: list[ToolResult] = []
            for call in tool_calls:
                budget.consume_tool_call()
                try:
                    res = await self._executor.execute_tool(call)
                    tool_results.append(res)
                except Exception as exc:
                    tool_results.append(ToolResult(success=False, data=None, error=str(exc), tool_name=call.tool_name))

            state.last_results = tool_results

            # 5. EVALUATE: Verifikasi hasil secara objektif via ObjectiveEvaluator
            eval_res = self.evaluator.evaluate_tool_results(tool_results)
            state.last_eval = eval_res

            if eval_res.is_verified:
                yield f"\n✔ [Objective Evaluator] Verifikasi SUKSES (Confidence: {eval_res.confidence_score:.2f})\n"
                state.status = "completed"
                break
            else:
                yield f"\n❌ [Objective Evaluator] Verifikasi GAGAL: {', '.join(eval_res.failure_reasons)}\n"
                yield "🔄 [Re-planning] Melakukan penyesuaian strategi di iterasi berikutnya...\n\n"
                budget.increment_retry()


__all__ = ["TaskState", "AgentController"]
