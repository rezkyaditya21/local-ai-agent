"""
agent/core/evaluator.py

Objective Evaluator — memverifikasi hasil eksekusi berdasarkan bukti objektif (bukan klaim teks LLM).

Komponen utama:
- `VerificationResult`: Dataclass hasil verifikasi objektif.
- `ObjectiveEvaluator`: Verifikator berbasis bukti (exit code, pytest, logs, static analysis, filesystem).
"""

from __future__ import annotations

import ast
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agent.models.schemas import ToolResult

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
