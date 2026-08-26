"""
tests/unit/test_self_improvement_engine.py

Unit test untuk SelfImprovementEngine dan CheckpointManager.
"""

from __future__ import annotations

import pytest
from pathlib import Path
from agent.self_improvement.checkpoint import CheckpointManager
from agent.self_improvement.engine import SelfImprovementEngine


def test_checkpoint_creation_and_restore(tmp_path: Path) -> None:
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "app.py").write_text("print('v1')", encoding="utf-8")

    ckpt_dir = tmp_path / "checkpoints"
    mgr = CheckpointManager(checkpoint_dir=ckpt_dir)

    checkpoint_path = mgr.create_checkpoint(source_dir, tag="v1")
    assert checkpoint_path.exists()

    # Ubah source
    (source_dir / "app.py").write_text("print('v2')", encoding="utf-8")
    assert (source_dir / "app.py").read_text() == "print('v2')"

    # Rollback
    success = mgr.restore_checkpoint(checkpoint_path, source_dir)
    assert success is True
    assert (source_dir / "app.py").read_text() == "print('v1')"
