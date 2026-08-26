"""
agent/self_improvement/engine.py

Self-Improvement Engine — melakukan eksperimen terkontrol pada kode sumber:
Hipotesis → Perubahan → Test → Benchmark → Evaluasi → Commit / Rollback.

Komponen utama:
- `ExperimentResult`: Dataclass hasil eksperimen.
- `SelfImprovementEngine`: Mesin eksperimen dan perbaikan mandiri.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent.self_improvement.checkpoint import CheckpointManager
from agent.tools.benchmark import BenchmarkTool
from agent.tools.test_runner import TestRunnerTool

_logger = logging.getLogger(__name__)


@dataclass
class ExperimentResult:
    """Hasil eksperimen terkontrol pada kode sumber."""

    hypothesis: str
    passed_tests: bool
    benchmark_improvement_percent: float
    retained: bool
    details: str


class SelfImprovementEngine:
    """Mesin perbaikan dan eksperimen terkontrol mandiri."""

    def __init__(
        self,
        checkpoint_manager: CheckpointManager | None = None,
        test_runner: TestRunnerTool | None = None,
        benchmark_tool: BenchmarkTool | None = None,
    ) -> None:
        self._checkpoint_mgr = checkpoint_manager or CheckpointManager()
        self._test_runner = test_runner or TestRunnerTool()
        self._benchmark_tool = benchmark_tool or BenchmarkTool()

    async def run_experiment(
        self,
        hypothesis: str,
        target_file: Path,
        modified_content: str,
        project_root: Path,
    ) -> ExperimentResult:
        """Jalankan siklus eksperimen terkontrol:

        1. Buat checkpoint snapshot.
        2. Terapkan perubahan pada target_file.
        3. Jalankan unit test (test_runner).
        4. Jika test gagal -> ROLLBACK otomatis.
        5. Jika test lulus -> PERTAHANKAN perubahan.
        """
        _logger.info("Memulai eksperimen: '%s'", hypothesis)
        checkpoint_path = self._checkpoint_mgr.create_checkpoint(project_root, tag="experiment")

        original_content = ""
        if target_file.exists():
            original_content = target_file.read_text(encoding="utf-8")

        # Terapkan perubahan
        try:
            target_file.write_text(modified_content, encoding="utf-8")
        except Exception as exc:
            self._checkpoint_mgr.restore_checkpoint(checkpoint_path, project_root)
            return ExperimentResult(
                hypothesis=hypothesis,
                passed_tests=False,
                benchmark_improvement_percent=0.0,
                retained=False,
                details=f"Gagal menulis perubahan: {exc}",
            )

        # Jalankan pengujian
        test_result = await self._test_runner.run({"test_path": "tests"})

        if not test_result.success:
            _logger.warning("Pengujian gagal setelah eksperimen. Melakukan ROLLBACK otomatis...")
            self._checkpoint_mgr.restore_checkpoint(checkpoint_path, project_root)
            return ExperimentResult(
                hypothesis=hypothesis,
                passed_tests=False,
                benchmark_improvement_percent=0.0,
                retained=False,
                details=f"Tes gagal: {test_result.error}",
            )

        # Tes lulus — pertahankan perubahan!
        _logger.info("Eksperimen berhasil dan tes lulus 100%. Perubahan DIPERTAHANKAN.")
        return ExperimentResult(
            hypothesis=hypothesis,
            passed_tests=True,
            benchmark_improvement_percent=0.0,
            retained=True,
            details="Perubahan berhasil diverifikasi dan lulus seluruh unit tes.",
        )


__all__ = ["ExperimentResult", "SelfImprovementEngine"]
