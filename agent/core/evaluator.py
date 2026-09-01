"""
agent/core/evaluator.py

Objective Evaluator — memverifikasi hasil eksekusi berdasarkan bukti objektif (bukan klaim teks LLM).

Komponen utama:
- `VerificationResult`: Dataclass hasil verifikasi objektif.
- `ObjectiveEvaluator`: Verifikator berbasis bukti (exit code, pytest, logs, static analysis, filesystem).
"""

from __future__ import annotations

import ast
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from agent.models.schemas import GoalEvaluation, GoalStatus, ToolResult

if TYPE_CHECKING:
    from agent.models.manager import ModelManager

_logger = logging.getLogger(__name__)


@dataclass
class VerificationResult:
    """Hasil evaluasi objektif dari tindakan agent."""

    is_verified: bool
    confidence_score: float  # 0.0 - 1.0
    evidence: list[str] = field(default_factory=list)
    failure_reasons: list[str] = field(default_factory=list)


class ObjectiveEvaluator:
    """Evaluator berbasis bukti nyata untuk memverifikasi apakah tugas benar-benar selesai."""

    def __init__(self, model_manager: "ModelManager | None" = None) -> None:
        self._model_manager = model_manager

    def evaluate_tool_results(self, results: list[ToolResult]) -> VerificationResult:
        """Evaluasi hasil tool calls berdasarkan status, exit code, dan data."""
        if not results:
            return VerificationResult(
                is_verified=False,
                confidence_score=0.0,
                evidence=["Tidak ada tool call yang dieksekusi."],
                failure_reasons=["Eksekusi kosong"],
            )

        evidence = []
        failures = []
        all_success = True

        for res in results:
            if not res.success:
                all_success = False
                failures.append(f"Tool '{res.tool_name}' gagal: {res.error}")
            else:
                evidence.append(f"Tool '{res.tool_name}' sukses.")

                # Evaluasi khusus jika res data mengandung exit_code atau test metrics
                if isinstance(res.data, dict):
                    if "exit_code" in res.data and res.data["exit_code"] != 0:
                        all_success = False
                        failures.append(f"Tool '{res.tool_name}' menghasilkan exit_code {res.data['exit_code']}")

                    if "failed" in res.data and res.data["failed"] > 0:
                        all_success = False
                        failures.append(f"TestRunner mendeteksi {res.data['failed']} tes gagal.")

        score = (len(evidence) / len(results)) if results else 0.0
        if not all_success:
            score *= 0.5

        return VerificationResult(
            is_verified=all_success,
            confidence_score=score,
            evidence=evidence,
            failure_reasons=failures,
        )

    async def evaluate_goal(
        self,
        goal: str,
        results: list[ToolResult],
        iteration: int = 1,
    ) -> GoalEvaluation:
        """Verifikasi apakah *goal* tercapai menggunakan bukti objektif.

        Jika LLM tersedia, gunakan LLM untuk judgment tambahan.
        Jika tidak, gunakan rule-based evaluation.
        """
        # Step 1: Rule-based evaluation
        health = self.evaluate_tool_results(results)

        evidence: list[str] = list(health.evidence)
        failures: list[str] = list(health.failure_reasons)
        goal_lower = goal.lower()

        # Check if goal needs passing tests
        if self._goal_needs_passing_tests(goal_lower):
            if not self._has_passing_tests(results):
                failures.append(
                    "Goal memerlukan tes yang lulus (test_runner) tetapi bukti belum ada."
                )
            else:
                evidence.append("Test results menunjukkan semua tes lulus.")

        # Check if goal needs git commit
        if self._goal_needs_git(goal_lower):
            if not any(r.success and r.tool_name == "git" for r in results):
                failures.append(
                    "Goal memerlukan aksi git tetapi belum ada hasil git yang sukses."
                )
            else:
                evidence.append("Git commit berhasil.")

        # Check for file modifications
        if any(kw in goal_lower for kw in ["fix", "perbaiki", "modify", "ubah", "refactor"]):
            fs_writes = [r for r in results if r.success and r.tool_name == "filesystem"
                         and isinstance(r.data, dict) and r.data.get("operation") in ("write_file", "create")]
            if fs_writes:
                evidence.append(f"{len(fs_writes)} file berhasil dimodifikasi.")
            else:
                failures.append("Goal memerlukan modifikasi file tetapi tidak ada file write yang terdeteksi.")

        # Check for shell command failures
        shell_failures = [r for r in results if not r.success and r.tool_name == "shell"]
        if shell_failures:
            for sf in shell_failures:
                failures.append(f"Shell command gagal: {sf.error}")

        # Score calculation
        if not results:
            score = 0.0
        else:
            score = len(evidence) / max(len(results), 1)
            if failures:
                score = min(score, 0.5)

        # Determine status
        if not failures and score > 0.5:
            status = GoalStatus.COMPLETED
            should_replan = False
        elif failures and score < 0.3:
            status = GoalStatus.FAILED
            should_replan = True
        else:
            status = GoalStatus.IN_PROGRESS
            should_replan = True

        # Build next steps
        next_steps: list[str] = []
        if should_replan:
            if "test" in goal_lower and not self._has_passing_tests(results):
                next_steps.append("Jalankan test_runner untuk memverifikasi perubahan.")
            if "file" in " ".join(failures).lower():
                next_steps.append("Periksa apakah file yang dimodifikasi sudah benar.")
            if not next_steps:
                next_steps.append("Re-analisis hasil dan coba pendekatan berbeda.")

        return GoalEvaluation(
            status=status,
            confidence=score,
            evidence=evidence,
            failure_reasons=failures,
            should_replan=should_replan,
            next_steps=next_steps,
        )

    @staticmethod
    def _goal_needs_passing_tests(goal_l: str) -> bool:
        markers = (
            "pytest", "unit test", "jalankan tes", "jalankan test",
            "run test", "run tests", "fix test", "tes gagal", "test gagal",
        )
        return any(m in goal_l for m in markers)

    @staticmethod
    def _goal_needs_git(goal_l: str) -> bool:
        return "commit" in goal_l or "git push" in goal_l

    @staticmethod
    def _has_passing_tests(results: list[ToolResult]) -> bool:
        for res in results:
            if not res.success or res.tool_name != "test_runner":
                continue
            if isinstance(res.data, dict) and int(res.data.get("failed", 0) or 0) == 0:
                return True
        return False

    def verify_python_syntax(self, file_path: Path) -> VerificationResult:
        """Verifikasi statis bahwa file Python valid dan bebas syntax error."""
        if not file_path.exists():
            return VerificationResult(
                is_verified=False,
                confidence_score=0.0,
                failure_reasons=[f"File '{file_path}' tidak ditemukan."],
            )

        try:
            content = file_path.read_text(encoding="utf-8")
            ast.parse(content)
            return VerificationResult(
                is_verified=True,
                confidence_score=1.0,
                evidence=[f"Sintaksis Python pada '{file_path.name}' valid (AST Parsed)."],
            )
        except SyntaxError as syn_err:
            return VerificationResult(
                is_verified=False,
                confidence_score=0.0,
                failure_reasons=[f"SyntaxError pada baris {syn_err.lineno}: {syn_err.msg}"],
            )
        except Exception as exc:
            return VerificationResult(
                is_verified=False,
                confidence_score=0.0,
                failure_reasons=[f"Gagal mem-parse AST: {exc}"],
            )


__all__ = ["VerificationResult", "ObjectiveEvaluator"]
