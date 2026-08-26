"""
agent/self_improvement/checkpoint.py

Checkpoint Manager — membuat snapshot cadangan berkas sumber dan memulihkannya jika terjadi regresi/kegagalan.

Komponen utama:
- `CheckpointManager`: Pengelola snapshot pemulihan.
"""

from __future__ import annotations

import logging
import shutil
import time
from pathlib import Path
from typing import Any

_logger = logging.getLogger(__name__)


class CheckpointManager:
    """Pengelola cadangan snapshot repositori/berkas sumber sebelum self-modification."""

    def __init__(self, checkpoint_dir: Path | None = None) -> None:
        self._dir = checkpoint_dir or (Path.home() / ".config" / "local-ai-agent" / "checkpoints")
        self._dir.mkdir(parents=True, exist_ok=True)

    def create_checkpoint(self, source_dir: Path, tag: str = "") -> Path:
        """Buat snapshot cadangan direktori sumber saat ini."""
        timestamp = int(time.time())
        checkpoint_name = f"snapshot_{timestamp}" + (f"_{tag}" if tag else "")
        dest = self._dir / checkpoint_name
        dest.mkdir(parents=True, exist_ok=True)

        for item in source_dir.iterdir():
            if item.name in (".git", "__pycache__", ".pytest_cache", ".venv", "venv", "node_modules"):
                continue
            target = dest / item.name
            if item.is_dir():
                shutil.copytree(item, target, dirs_exist_ok=True)
            else:
                shutil.copy2(item, target)

        _logger.info("Checkpoint dibuat di: %s", dest)
        return dest

    def restore_checkpoint(self, checkpoint_path: Path, target_dir: Path) -> bool:
        """Pulihkan snapshot cadangan ke direktori target."""
        if not checkpoint_path.exists():
            _logger.error("Path checkpoint tidak ditemukan: %s", checkpoint_path)
            return False

        try:
            for item in checkpoint_path.iterdir():
                target = target_dir / item.name
                if item.is_dir():
                    shutil.copytree(item, target, dirs_exist_ok=True)
                else:
                    shutil.copy2(item, target)
            _logger.info("Berhasil memulihkan checkpoint dari %s ke %s", checkpoint_path, target_dir)
            return True
        except Exception as exc:
            _logger.error("Gagal memulihkan checkpoint: %s", exc)
            return False


__all__ = ["CheckpointManager"]
