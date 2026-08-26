"""Self-improvement layer — config proposals, plugin loader, backup manager, engine, checkpoint."""

from agent.self_improvement.backup_manager import BackupManager
from agent.self_improvement.checkpoint import CheckpointManager
from agent.self_improvement.engine import ExperimentResult, SelfImprovementEngine
from agent.self_improvement.module import SelfImprovementModule

__all__ = [
    "BackupManager",
    "CheckpointManager",
    "ExperimentResult",
    "SelfImprovementEngine",
    "SelfImprovementModule",
]
