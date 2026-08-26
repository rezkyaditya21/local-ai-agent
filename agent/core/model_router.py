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
            # Gunakan active model sebagai fallback
            active = self._model_manager.get_active_model()
            return active.name if active else "default"

        # Cari model yang cocok dengan kata kunci kategori
        category_lower = category.lower()
        for cfg in available:
            name_lower = cfg.name.lower()
            if category_lower == "coding" and ("coder" in name_lower or "code" in name_lower):
                return cfg.name
            if category_lower == "reasoning" and ("reason" in name_lower or "r1" in name_lower or "70b" in name_lower):
                return cfg.name
            if category_lower == "fast" and ("3b" in name_lower or "small" in name_lower or "fast" in name_lower):
                return cfg.name

        # Fallback ke model aktif
        active = self._model_manager.get_active_model()
        return active.name if active else available[0].name


__all__ = ["ModelRouter"]
