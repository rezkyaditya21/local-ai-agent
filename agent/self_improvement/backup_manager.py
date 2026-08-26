"""
agent/self_improvement/backup_manager.py

BackupManager: manages versioned JSON backups of agent configuration.

Backup files are named with a timestamp:
    backup_YYYYMMDD_HHMMSS_ffffff.json

At most 10 backup versions are retained; the oldest are pruned automatically
after every call to `create_backup`.

Requirements: 8.7, 8.8
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

MAX_BACKUP_VERSIONS = 10


class BackupManager:
    """Manages versioned backups of agent configuration.

    Backups are stored as JSON files inside *backup_dir*.  The directory is
    created automatically when the first backup is written.

    Args:
        backup_dir: Directory where backup files will be stored.
    """

    def __init__(self, backup_dir: Path) -> None:
        self.backup_dir = Path(backup_dir)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create_backup(self, config: dict) -> str:
        """Serialise *config* to a timestamped JSON file and return its path.

        After writing the new backup the oldest files are pruned so that
        at most :data:`MAX_BACKUP_VERSIONS` (10) backup files remain.

        Args:
            config: Configuration dictionary to back up.

        Returns:
            Absolute path of the newly created backup file as a string.
        """
        self.backup_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        filename = f"backup_{timestamp}.json"
        backup_path = self.backup_dir / filename

        backup_path.write_text(
            json.dumps(config, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        self._prune()

        return str(backup_path)

    def get_latest(self) -> dict | None:
        """Return the most recent backup as a dict, or ``None`` if none exist.

        Returns:
            Parsed JSON dict of the latest backup, or ``None``.
        """
        backups = self.list_backups()
        if not backups:
            return None

        latest = backups[0]  # list_backups returns newest-first
        return json.loads(latest.read_text(encoding="utf-8"))

    def list_backups(self) -> list[Path]:
        """Return all backup files sorted newest-first, at most 10 entries.

        The directory is not created here; an absent directory simply means
        no backups exist yet.

        Returns:
            List of :class:`~pathlib.Path` objects, newest backup first,
            capped at :data:`MAX_BACKUP_VERSIONS`.
        """
        if not self.backup_dir.exists():
            return []

        files = sorted(
            self.backup_dir.glob("backup_*.json"),
            key=lambda p: p.name,
            reverse=True,  # lexicographic DESC → newest timestamp first
        )
        return files[:MAX_BACKUP_VERSIONS]

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _prune(self) -> None:
        """Delete the oldest backup files that exceed MAX_BACKUP_VERSIONS."""
        if not self.backup_dir.exists():
            return

        # Sort oldest-first so we delete from the front
        all_files = sorted(
            self.backup_dir.glob("backup_*.json"),
            key=lambda p: p.name,
        )

        excess = len(all_files) - MAX_BACKUP_VERSIONS
        if excess <= 0:
            return
        for old_file in all_files[:excess]:
            try:
                old_file.unlink()
            except OSError:
                pass  # Best-effort; missing file is not critical
