"""
agent/core/scheduler.py

TaskScheduler — penjadwal tugas otomatis dan cron di latar belakang (Hermes-inspired).
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Coroutine

_logger = logging.getLogger(__name__)

DEFAULT_SCHEDULER_STORAGE = "scheduler.json"


@dataclass
class ScheduledTask:
    """Representasi satu tugas terjadwal."""

    id: str
    name: str
    goal: str
    interval_seconds: int = 3600  # Default: 1 jam
    cron_expr: str = ""  # Format cron opsional
    enabled: bool = True
    target_gateway: str = "cli"  # "cli" atau "telegram"
    last_run: str | None = None
    last_status: str = "never_run"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def is_due(self) -> bool:
        """Cek apakah tugas sudah waktunya dijalankan."""
        if not self.enabled:
            return False
        if self.last_run is None:
            return True
        try:
            last_dt = datetime.fromisoformat(self.last_run)
            now = datetime.now(timezone.utc)
            elapsed = (now - last_dt).total_seconds()
            return elapsed >= self.interval_seconds
        except Exception:
            return True


class TaskScheduler:
    """Pengelola eksekusi tugas otonom terjadwal."""

    def __init__(
        self,
        storage_path: Path | None = None,
        task_executor: Callable[[str], Coroutine[Any, Any, str]] | None = None,
    ) -> None:
        self._storage_path = storage_path or (
            Path.home() / ".config" / "local-ai-agent" / DEFAULT_SCHEDULER_STORAGE
        )
        self._tasks: dict[str, ScheduledTask] = {}
        self._task_executor = task_executor
        self._running = False
        self._loop_task: asyncio.Task | None = None
        self._load_storage()

    def set_executor(self, executor: Callable[[str], Coroutine[Any, Any, str]]) -> None:
        """Set fungsi callback eksekutor tugas."""
        self._task_executor = executor

    def add_task(
        self,
        name: str,
        goal: str,
        interval_seconds: int = 3600,
        cron_expr: str = "",
        target_gateway: str = "cli",
    ) -> ScheduledTask:
        """Tambahkan tugas baru ke daftar cron scheduler."""
        import uuid

        task_id = str(uuid.uuid4())[:8]
        task = ScheduledTask(
            id=task_id,
            name=name,
            goal=goal,
            interval_seconds=interval_seconds,
            cron_expr=cron_expr,
            target_gateway=target_gateway,
        )
        self._tasks[task_id] = task
        self._save_storage()
        _logger.info("Tugas terjadwal ditambahkan: [%s] %s", task_id, name)
        return task

    def remove_task(self, task_id: str) -> bool:
        """Hapus tugas terjadwal berdasarkan ID."""
        if task_id in self._tasks:
            del self._tasks[task_id]
            self._save_storage()
            return True
        return False

    def list_tasks(self) -> list[ScheduledTask]:
        """Ambil seluruh daftar tugas terjadwal."""
        return list(self._tasks.values())

    def get_task(self, task_id: str) -> ScheduledTask | None:
        """Ambil detail tugas berdasarkan ID."""
        return self._tasks.get(task_id)

    def toggle_task(self, task_id: str, enabled: bool) -> bool:
        """Aktifkan atau nonaktifkan tugas."""
        if task_id in self._tasks:
            self._tasks[task_id].enabled = enabled
            self._save_storage()
            return True
        return False

    async def run_due_tasks(self) -> list[dict[str, Any]]:
        """Jalankan semua tugas yang sudah jatuh tempo."""
        results = []
        for task in list(self._tasks.values()):
            if task.is_due() and self._task_executor is not None:
                _logger.info("Menjalankan tugas cron: [%s] %s", task.id, task.name)
                task.last_run = datetime.now(timezone.utc).isoformat()
                task.last_status = "running"
                self._save_storage()

                try:
                    output = await self._task_executor(task.goal)
                    task.last_status = "success"
                    results.append({"task_id": task.id, "name": task.name, "status": "success", "output": output})
                except Exception as exc:
                    task.last_status = f"failed: {exc}"
                    results.append({"task_id": task.id, "name": task.name, "status": "failed", "error": str(exc)})
                finally:
                    self._save_storage()
        return results

    async def _scheduler_loop(self, check_interval_seconds: int = 30) -> None:
        """Loop latar belakang untuk memeriksa tugas jatuh tempo secara berkala."""
        while self._running:
            try:
                await self.run_due_tasks()
            except Exception as exc:
                _logger.error("Error dalam loop scheduler: %s", exc)
            await asyncio.sleep(check_interval_seconds)

    def start(self, check_interval_seconds: int = 30) -> None:
        """Mulai loop scheduler di background asyncio."""
        if not self._running:
            self._running = True
            try:
                loop = asyncio.get_running_loop()
                self._loop_task = loop.create_task(self._scheduler_loop(check_interval_seconds))
            except RuntimeError:
                pass

    def stop(self) -> None:
        """Hentikan scheduler background."""
        self._running = False
        if self._loop_task and not self._loop_task.done():
            self._loop_task.cancel()
            self._loop_task = None

    def _load_storage(self) -> None:
        if not self._storage_path.exists():
            return
        try:
            with open(self._storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for t_id, t_dict in data.items():
                self._tasks[t_id] = ScheduledTask(**t_dict)
        except Exception as exc:
            _logger.warning("Gagal membaca storage scheduler: %s", exc)

    def _save_storage(self) -> None:
        try:
            self._storage_path.parent.mkdir(parents=True, exist_ok=True)
            data = {t_id: asdict(task) for t_id, task in self._tasks.items()}
            with open(self._storage_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as exc:
            _logger.warning("Gagal menyimpan storage scheduler: %s", exc)


__all__ = ["ScheduledTask", "TaskScheduler"]
