"""
agent/core/controller.py

Agent Controller — pusat orchestration untuk closed-loop autonomous execution.

Alur utama:
  OBSERVE -> ANALYZE -> PLAN -> ACT -> OBSERVE RESULT -> EVALUATE -> REPLAN/VERIFY -> REPEAT

Komponen utama:
- `TaskState`: State komprehensif dari sebuah tugas sepanjang iterasi.
- `AgentController`: Pengendali closed-loop execution loop.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, AsyncIterator

from agent.core.audit_logger import AuditLogger
from agent.core.budget import ExecutionBudget
from agent.core.capabilities import CapabilityManager, CapabilityMap
from agent.core.evaluator import ObjectiveEvaluator, VerificationResult
from agent.core.model_router import ModelRouter
from agent.core.planner import ExecutionPlan, MultiStepPlanner, SubTask
from agent.memory.memory_system import MemorySystem
from agent.models.schemas import GoalEvaluation, GoalStatus, TaskPlan, ToolCall, ToolResult
from agent.self_improvement.checkpoint import CheckpointManager
from agent.tools.registry import ToolRegistry

if TYPE_CHECKING:
    from agent.core.executor import Executor
    from agent.models.manager import ModelManager

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tool call parser (dari orchestrator.py)
# ---------------------------------------------------------------------------

def _extract_json_objects(text: str) -> list[str]:
    """Ekstrak semua JSON object top-level dari teks secara iteratif."""
    objects: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        if text[i] != "{":
            i += 1
            continue
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
    """Cari dan parse semua JSON tool call block dari teks output model."""
    calls: list[ToolCall] = []
    for raw in _extract_json_objects(text):
        try:
            data: dict = json.loads(raw)
        except json.JSONDecodeError:
            continue

        if not isinstance(data, dict):
            continue

        tool_name: str = data.get("tool") or data.get("tool_name") or data.get("name") or ""
        op = data.get("operation", "")
        if not tool_name:
            if op in ("system_telemetry", "fast_scan", "fast_grep"):
                tool_name = "rust_core"
            elif op in ("view", "write", "replace"):
                tool_name = "file_editor"
            elif op == "run_command" or "command" in data:
                tool_name = "shell"

        params: dict = data.get("params", {})
        if not params and isinstance(data, dict):
            params = {k: v for k, v in data.items() if k not in ("tool", "tool_name", "name")}

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


def _utc_now_iso() -> str:
    """Kembalikan timestamp UTC saat ini dalam format ISO 8601."""
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


# ---------------------------------------------------------------------------
# TaskState
# ---------------------------------------------------------------------------

@dataclass
class TaskState:
    """State tugas otonom yang dipertahankan sepanjang iterasi."""

    goal: str
    iteration: int = 0
    status: str = "in_progress"  # "in_progress" | "completed" | "failed" | "exhausted"
    plan: ExecutionPlan | None = None
    last_results: list[ToolResult] = field(default_factory=list)
    last_eval: GoalEvaluation | None = None
    all_results: list[ToolResult] = field(default_factory=list)
    execution_logs: list[str] = field(default_factory=list)
    tool_calls_this_iter: list[ToolCall] = field(default_factory=list)


# ---------------------------------------------------------------------------
# AgentController
# ---------------------------------------------------------------------------

class AgentController:
    """Agent Controller sentral untuk mengkoordinasikan seluruh subsistem dalam closed-loop execution.

    Alur utama:
        OBSERVE -> PLAN -> ACT -> EVALUATE -> REPLAN/VERIFY -> REPEAT
    """

    def __init__(
        self,
        model_manager: "ModelManager",
        executor: "Executor",
        registry: ToolRegistry | None = None,
        audit_logger: AuditLogger | None = None,
        memory_system: MemorySystem | None = None,
        planner: MultiStepPlanner | None = None,
        evaluator: ObjectiveEvaluator | None = None,
        capability_mgr: CapabilityManager | None = None,
        model_router: ModelRouter | None = None,
        checkpoint_mgr: CheckpointManager | None = None,
    ) -> None:
        self._model_manager = model_manager
        self._executor = executor
        self._registry = registry or getattr(executor, "_registry", ToolRegistry())
        self._audit_logger = audit_logger

        self.memory = memory_system or MemorySystem()
        self.planner = planner or MultiStepPlanner()
        self.evaluator = evaluator or ObjectiveEvaluator(model_manager=model_manager)
        self.capability_mgr = capability_mgr or CapabilityManager()
        self.model_router = model_router or ModelRouter(model_manager)
        self.checkpoint_mgr = checkpoint_mgr or CheckpointManager()

    async def execute_task(
        self,
        goal: str,
        budget: ExecutionBudget | None = None,
        yield_tokens: bool = True,
    ) -> AsyncIterator[str]:
        """Jalankan Closed-Loop Autonomous Loop:
        OBSERVE -> ANALYZE -> PLAN -> ACT -> OBSERVE RESULT -> EVALUATE -> REPLAN/VERIFY -> REPEAT.

        Args:
            goal: Tujuan utama dari pengguna.
            budget: Anggaran eksekusi opsional.
            yield_tokens: Jika True, yield progress tokens untuk streaming ke CLI.

        Yields:
            Token string streaming untuk pemanggil.
        """
        budget = budget or ExecutionBudget()

        # =========================================================================
        # OBSERVE: Deteksi capabilities, build context
        # =========================================================================
        cap_map = self.capability_mgr.detect_capabilities()
        model_names = [m.name for m in self._model_manager.list_models()]
        self.capability_mgr._map.available_models = model_names
        cap_context = cap_map.to_prompt_context()

        # Ambil tool catalog
        tool_catalog = self._registry.format_catalog()

        # Ambil memory context
        memory_ctx = self.memory.build_context_for_goal(goal)
        from agent.core.prompting import build_memory_context
        memory_text = build_memory_context(
            working=memory_ctx.get("working"),
            task_history=memory_ctx.get("task_history"),
            long_term=memory_ctx.get("long_term"),
            project_knowledge=memory_ctx.get("project_knowledge"),
            self_knowledge=memory_ctx.get("self_knowledge"),
        )

        # =========================================================================
        # INIT: Setup state
        # =========================================================================
        state = TaskState(goal=goal)

        if yield_tokens:
            yield f"AgentController: Memulai tugas otonom: '{goal}'\n"
            yield f"Capabilities: {cap_map.os_platform} | Python {cap_map.python_version} | Tools: {len(self._registry.list_all())}\n"
            yield f"Budget: {budget.remaining_summary()}\n\n"

        self._audit_logger and self._audit_logger.log_action(
            action="agent.task_start",
            params={"goal": goal},
            result="started",
            confirmed=True,
        )

        # =========================================================================
        # MAIN LOOP: OBSERVE -> PLAN -> ACT -> EVALUATE -> REPEAT
        # =========================================================================
        while True:
            # 1. Periksa budget
            is_exhausted, reason = budget.is_exhausted()
            if is_exhausted:
                state.status = GoalStatus.EXHAUSTED
                if yield_tokens:
                    yield f"\nBudget habis: {reason}\n"
                    yield f"{budget.remaining_summary()}\n"
                self._audit_logger and self._audit_logger.log_action(
                    action="agent.budget_exhausted",
                    params={"goal": goal, "iteration": state.iteration},
                    result=reason,
                    confirmed=True,
                )
                break

            budget.consume_iteration()
            state.iteration = budget.current_iteration

            if yield_tokens:
                yield f"\n--- Iterasi {state.iteration}/{budget.max_iterations} ---\n"

            # 2. OBSERVE: Update memory context untuk iterasi ini
            memory_ctx = self.memory.build_context_for_goal(goal)
            memory_text = build_memory_context(
                working=memory_ctx.get("working"),
                task_history=memory_ctx.get("task_history"),
                long_term=memory_ctx.get("long_term"),
                project_knowledge=memory_ctx.get("project_knowledge"),
                self_knowledge=memory_ctx.get("self_knowledge"),
            )

            # 3. PLAN & ACT: Pilih model, bangun prompt, generate
            model_name = self.model_router.select_model_for_task(
                "reasoning" if state.iteration == 1 else "coding"
            )

            if yield_tokens:
                yield f"Model: {model_name}\n"

            from agent.core.prompting import build_task_prompt
            prompt = build_task_prompt(
                goal=goal,
                tool_catalog=tool_catalog,
                iteration=state.iteration,
                budget_summary=budget.remaining_summary(),
                memory_text=memory_text,
                capability_text=cap_context,
                last_results=state.last_results if state.last_results else None,
                last_eval=None,
            )

            # Generate response dari model
            collected_tokens: list[str] = []
            try:
                async for token in self._model_manager.generate(
                    prompt=prompt,
                    history=[],
                    model_name=model_name,
                ):
                    collected_tokens.append(token)
                    if yield_tokens:
                        yield token
            except Exception as exc:
                if yield_tokens:
                    yield f"\n[Error Model: {exc}]\n"
                self._audit_logger and self._audit_logger.log_error(
                    error=str(exc),
                    context={"goal": goal, "iteration": state.iteration, "phase": "generate"},
                )
                # Don't break — try replanning
                budget.increment_retry()
                continue

            response_text = "".join(collected_tokens)

            # 4. Parse tool calls dari response
            tool_calls = _parse_tool_calls(response_text)

            if not tool_calls:
                # Tidak ada tool call — model mungkin sudah selesai
                # Tapi kita harus verify via evaluator
                if yield_tokens:
                    yield "\n[Model tidak menghasilkan tool call]\n"

                # Verifikasi apakah tujuan benar-benar tercapai
                eval_result = await self._evaluate_goal_with_model(
                    goal, state.all_results, state.iteration
                )
                state.last_eval = eval_result

                if eval_result.status == GoalStatus.COMPLETED:
                    state.status = GoalStatus.COMPLETED
                    if yield_tokens:
                        yield f"\nTujuan tercapai! (confidence: {eval_result.confidence:.2f})\n"
                        for e in eval_result.evidence:
                            yield f"  Bukti: {e}\n"
                    # Store success ke memory
                    self.memory.store_task_result(goal, "completed without additional tools", True)
                    self._audit_logger and self._audit_logger.log_action(
                        action="agent.task_complete",
                        params={"goal": goal, "iteration": state.iteration},
                        result=f"completed, confidence={eval_result.confidence:.2f}",
                        confirmed=True,
                    )
                    break
                else:
                    # Belum selesai — replan
                    if yield_tokens:
                        yield f"Evaluasi: {eval_result.status} (confidence: {eval_result.confidence:.2f})\n"
                        for fr in eval_result.failure_reasons:
                            yield f"  {fr}\n"
                    budget.increment_retry()
                    continue

            # 5. ACT: Eksekusi tool calls
            if yield_tokens:
                yield f"\nEksekusi {len(tool_calls)} tool calls...\n"

            tool_results: list[ToolResult] = []
            for call in tool_calls:
                budget.consume_tool_call()
                if yield_tokens:
                    yield f"  -> {call.tool_name}({call.params})\n"

                try:
                    res = await self._executor.execute(call)
                    tool_results.append(res)
                    state.all_results.append(res)

                    # Record task step ke memory
                    self.memory.add_task_step(
                        goal=goal,
                        step=state.iteration,
                        action=f"{call.tool_name}({json.dumps(call.params)[:100]})",
                        result="success" if res.success else f"failed: {res.error}",
                        status="completed" if res.success else "failed",
                    )

                    if yield_tokens:
                        status = "ok" if res.success else f"FAILED: {res.error}"
                        yield f"    {status}\n"

                except Exception as exc:
                    result = ToolResult(
                        success=False, data=None,
                        error=str(exc), tool_name=call.tool_name
                    )
                    tool_results.append(result)
                    state.all_results.append(result)
                    if yield_tokens:
                        yield f"    ERROR: {exc}\n"

                    # Record failure ke memory
                    self.memory.record_tool_failure(call.tool_name, str(exc)[:200])

            state.last_results = tool_results

            # 6. EVALUATE: Verifikasi hasil secara objektif
            eval_result = await self._evaluate_goal_with_model(
                goal, state.all_results, state.iteration
            )
            state.last_eval = eval_result

            if yield_tokens:
                yield f"\nEvaluasi: {eval_result.status} (confidence: {eval_result.confidence:.2f})\n"
                for e in eval_result.evidence[:3]:
                    yield f"  Bukti: {e}\n"
                for fr in eval_result.failure_reasons[:3]:
                    yield f"  Masalah: {fr}\n"

            # 7. DECISION: Complete / Replan / Failed
            if eval_result.status == GoalStatus.COMPLETED:
                state.status = GoalStatus.COMPLETED
                if yield_tokens:
                    yield f"\nTUGAS SELESAI! (confidence: {eval_result.confidence:.2f})\n"
                self.memory.store_task_result(goal, "completed successfully", True)
                self._audit_logger and self._audit_logger.log_action(
                    action="agent.task_complete",
                    params={"goal": goal, "iteration": state.iteration},
                    result=f"completed, confidence={eval_result.confidence:.2f}",
                    confirmed=True,
                )
                break

            elif eval_result.status == GoalStatus.FAILED and not eval_result.should_replan:
                state.status = GoalStatus.FAILED
                if yield_tokens:
                    yield f"\nTUGAS GAGAL: {eval_result.failure_reasons}\n"
                self.memory.store_task_result(goal, f"failed: {eval_result.failure_reasons}", False)
                self._audit_logger and self._audit_logger.log_action(
                    action="agent.task_failed",
                    params={"goal": goal, "iteration": state.iteration},
                    result=f"failed: {eval_result.failure_reasons}",
                    confirmed=True,
                )
                break

            elif eval_result.should_replan:
                # REPLAN: Buat rencana baru berdasarkan evaluasi
                if yield_tokens:
                    yield "Replanning...\n"
                    for ns in eval_result.next_steps:
                        yield f"  -> {ns}\n"

                state.plan = self.planner.replan(
                    plan=state.plan or ExecutionPlan(goal=goal),
                    evidence=eval_result.evidence,
                    failure_reasons=eval_result.failure_reasons,
                    next_steps=eval_result.next_steps,
                )
                budget.increment_retry()

            else:
                # IN_PROGRESS tapi tidak minta replan — lanjut
                budget.increment_retry()

        # =========================================================================
        # FINALIZE
        # =========================================================================
        if yield_tokens:
            yield f"\nSelesai. Status: {state.status} | Iterasi: {state.iteration} | "
            yield f"Tool calls: {budget.current_tool_calls} | "
            yield f"Waktu: {budget.remaining_summary()}\n"

        self.memory.clear_working()

    # ------------------------------------------------------------------
    # Evaluation helpers
    # ------------------------------------------------------------------

    async def _evaluate_goal_with_model(
        self,
        goal: str,
        results: list[ToolResult],
        iteration: int,
    ) -> GoalEvaluation:
        """Evaluasi goal — gunakan rule-based evaluator.

        Bisa dikembangkan untuk menggunakan LLM evaluator.
        """
        return await self.evaluator.evaluate_goal(
            goal=goal,
            results=results,
            iteration=iteration,
        )


__all__ = ["TaskState", "AgentController"]
