"""
agent/core/planner.py

Multi-Step Goal Planner — memecah instruksi kompleks menjadi rencana bertahap:
Goal → Subtasks → Actions → Verification → Final Result.

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


class MultiStepPlanner:
    """Pengelola rencana multi-step yang menguraikan tujuan menjadi subtask terstruktur."""

    def create_plan(self, goal: str, tool_calls: list[ToolCall]) -> ExecutionPlan:
        """Buat rencana eksekusi awal dari instruksi pengguna dan tool calls."""
        subtasks: list[SubTask] = []

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

        # Tambahkan langkah verifikasi otomatis jika ada tool_calls
        if subtasks:
            subtasks.append(
                SubTask(
                    id=len(subtasks) + 1,
                    description="Verifikasi dan sintesis hasil eksekusi",
                    action_type="verification",
                    status="pending",
                )
            )
        else:
            subtasks.append(
                SubTask(
                    id=1,
                    description="Analisis dan jawab instruksi secara langsung",
                    action_type="analysis",
                    status="pending",
                )
            )

        return ExecutionPlan(goal=goal, subtasks=subtasks)

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
