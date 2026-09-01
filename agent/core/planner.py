"""
agent/core/planner.py

Multi-Step Goal Planner — memecah instruksi kompleks menjadi rencana bertahap:
Goal -> Subtasks -> Actions -> Verification -> Final Result.

Komponen utama:
- `SubTask`: Dataclass untuk setiap langkah sub-tugas.
- `ExecutionPlan`: Rencana eksekusi lengkap dengan status kemajuan.
- `MultiStepPlanner`: Pengelola dan pembuat rencana bertahap.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from agent.models.schemas import ToolCall

_logger = logging.getLogger(__name__)


@dataclass
class SubTask:
    """Satu langkah sub-tugas dalam rencana eksekusi."""

    id: int
    description: str
    action_type: str     # "tool_call" | "verification" | "analysis"
    status: str          # "pending" | "in_progress" | "completed" | "failed"
    tool_call: ToolCall | None = None
    result_summary: str = ""


@dataclass
class ExecutionPlan:
    """Rencana eksekusi bertahap untuk mencapai tujuan (*Goal*)."""

    goal: str
    subtasks: list[SubTask] = field(default_factory=list)
    current_step: int = 0
    completed: bool = False

    @property
    def current_subtask(self) -> SubTask | None:
        if 0 <= self.current_step < len(self.subtasks):
            return self.subtasks[self.current_step]
        return None

    @property
    def pending_subtasks(self) -> list[SubTask]:
        return [s for s in self.subtasks if s.status == "pending"]

    @property
    def completed_count(self) -> int:
        return sum(1 for s in self.subtasks if s.status == "completed")

    @property
    def failed_count(self) -> int:
        return sum(1 for s in self.subtasks if s.status == "failed")

    def advance(self) -> None:
        """Majukan current_step ke subtask pending berikutnya."""
        if self.current_step < len(self.subtasks) - 1:
            self.current_step += 1

    def mark_all_completed(self) -> None:
        """Tandai semua subtask selesai."""
        for s in self.subtasks:
            if s.status != "failed":
                s.status = "completed"
        self.completed = True


class MultiStepPlanner:
    """Pengelola rencana multi-step yang menguraikan tujuan menjadi subtask terstruktur."""

    def create_plan(
        self,
        goal: str,
        tool_calls: list[ToolCall] | None = None,
        tool_catalog: str = "",
        memory_context: str = "",
        capability_context: str = "",
        previous_evidence: list[str] | None = None,
    ) -> ExecutionPlan:
        """Buat rencana eksekusi dari tujuan.

        Jika tool_calls diberikan (legacy mode), buat plan dari tool calls.
        Jika tidak, buat rencana kosong yang akan diisi oleh LLM di controller.
        """
        subtasks: list[SubTask] = []

        if tool_calls:
            # Legacy mode: wrap tool calls sebagai subtasks
            for idx, call in enumerate(tool_calls, start=1):
                subtasks.append(
                    SubTask(
                        id=idx,
                        description=f"Eksekusi tool '{call.tool_name}'",
                        action_type="tool_call",
                        status="pending",
                        tool_call=call,
                    )
                )
            # Tambahkan langkah verifikasi
            subtasks.append(
                SubTask(
                    id=len(subtasks) + 1,
                    description="Verifikasi dan sintesis hasil eksekusi",
                    action_type="verification",
                    status="pending",
                )
            )
        else:
            # Goal-based mode: buat rencana dasar
            # Subtask akan di-generate oleh LLM di controller
            subtasks.append(
                SubTask(
                    id=1,
                    description=f"Analisis dan pahami tujuan: {goal}",
                    action_type="analysis",
                    status="pending",
                )
            )

        return ExecutionPlan(goal=goal, subtasks=subtasks)

    def replan(
        self,
        plan: ExecutionPlan,
        evidence: list[str],
        failure_reasons: list[str],
        next_steps: list[str],
    ) -> ExecutionPlan:
        """Buat rencana baru berdasarkan hasil evaluasi sebelumnya.

        Args:
            plan: Rencana sebelumnya (dari iterasi lalu).
            evidence: Bukti yang sudah terkumpul.
            failure_reasons: Alasan kegagalan dari evaluator.
            next_steps: Saran langkah berikutnya dari evaluator.

        Returns:
            ExecutionPlan baru dengan subtask berdasarkan next_steps.
        """
        _logger.info(
            "Replanning: %d failure reasons, %d next steps",
            len(failure_reasons),
            len(next_steps),
        )

        # Preserve completed subtasks as history
        completed_tasks = [s for s in plan.subtasks if s.status == "completed"]

        # Build new subtasks from next_steps
        new_subtasks: list[SubTask] = []
        for idx, step in enumerate(next_steps, start=1):
            new_subtasks.append(
                SubTask(
                    id=idx,
                    description=step,
                    action_type="analysis",
                    status="pending",
                )
            )

        # If no next_steps provided, create a generic analysis step
        if not new_subtasks:
            new_subtasks.append(
                SubTask(
                    id=1,
                    description=f"Re-analisis tujuan: {plan.goal}",
                    action_type="analysis",
                    status="pending",
                )
            )

        # Add verification step
        new_subtasks.append(
            SubTask(
                id=len(new_subtasks) + 1,
                description="Verifikasi hasil replanning",
                action_type="verification",
                status="pending",
            )
        )

        return ExecutionPlan(
            goal=plan.goal,
            subtasks=new_subtasks,
            current_step=0,
            completed=False,
        )

    def update_subtask_status(self, plan: ExecutionPlan, subtask_id: int, status: str, result_summary: str = "") -> None:
        """Perbarui status subtask dan majukan `current_step` jika selesai."""
        for task in plan.subtasks:
            if task.id == subtask_id:
                task.status = status
                task.result_summary = result_summary
                break

        if status == "completed" and plan.current_step < len(plan.subtasks) - 1:
            plan.current_step += 1

        if all(task.status in ("completed", "failed") for task in plan.subtasks):
            plan.completed = True


__all__ = ["SubTask", "ExecutionPlan", "MultiStepPlanner"]
