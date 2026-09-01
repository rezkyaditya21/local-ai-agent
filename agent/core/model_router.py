"""
agent/core/model_router.py

Model Router — mengabstraksi pemilihan model berdasarkan kategori tugas (fast, coding, reasoning, evaluator).

Komponen utama:
- `ModelCategory`: Enum/String kategori model.
- `ModelRouter`: Pengarah rute model AI.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent.models.manager import ModelManager, ModelConfig

_logger = logging.getLogger(__name__)


class ModelRouter:
    """Pengarah rute model AI berdasarkan jenis dan kompleksitas tugas."""

    def __init__(self, model_manager: "ModelManager") -> None:
        self._model_manager = model_manager

    def select_model_for_task(self, category: str = "reasoning") -> str:
        """Pilih nama model terbaik untuk kategori tugas tertentu.

        Kategori:
        - "fast": untuk instruksi singkat atau pemilihan tool sederhana.
        - "coding": untuk modifikasi kode dan refactoring.
        - "reasoning": untuk analisis kompleks dan perencanaan.
        - "evaluator": untuk verifikasi hasil.

        Returns:
            Nama model aktif yang akan digunakan.
        """
        available = self._model_manager.list_models()
        if not available:
            active = self._model_manager.get_active_model()
            return active.name if active else "default"

        active = self._model_manager.get_active_model()
        active_name = active.name if active else None

        category_lower = category.lower()

        # Cari model yang cocok berdasarkan nama
        for cfg in available:
            name_lower = cfg.name.lower()
            if category_lower == "coding" and ("coder" in name_lower or "code" in name_lower):
                _logger.debug("ModelRouter: '%s' dipilih untuk kategori 'coding'", cfg.name)
                return cfg.name
            if category_lower == "reasoning" and ("reason" in name_lower or "r1" in name_lower or "70b" in name_lower):
                _logger.debug("ModelRouter: '%s' dipilih untuk kategori 'reasoning'", cfg.name)
                return cfg.name
            if category_lower == "fast" and ("3b" in name_lower or "small" in name_lower or "fast" in name_lower):
                _logger.debug("ModelRouter: '%s' dipilih untuk kategori 'fast'", cfg.name)
                return cfg.name
            if category_lower == "evaluator" and ("eval" in name_lower or "judge" in name_lower):
                _logger.debug("ModelRouter: '%s' dipilih untuk kategori 'evaluator'", cfg.name)
                return cfg.name

        # Fallback ke model aktif
        if active_name:
            _logger.debug("ModelRouter: fallback ke model aktif '%s'", active_name)
            return active_name

        # Fallback ke model pertama yang tersedia
        _logger.debug("ModelRouter: fallback ke model pertama '%s'", available[0].name)
        return available[0].name

    def get_model_info(self, model_name: str) -> dict | None:
        """Ambil informasi model berdasarkan nama."""
        available = self._model_manager.list_models()
        for cfg in available:
            if cfg.name == model_name:
                return {
                    "name": cfg.name,
                    "model_type": cfg.model_type,
                    "path_or_url": cfg.path_or_url,
                    "size_bytes": cfg.size_bytes,
                }
        return None


__all__ = ["ModelRouter"]
