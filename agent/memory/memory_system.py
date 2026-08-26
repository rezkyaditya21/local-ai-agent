"""
agent/memory/memory_system.py

Multi-Tiered Memory System — mengelola memori jangka pendek, memori kerja, memori jangka panjang, dan pengetahuan proyek.

Komponen utama:
- `MemorySystem`: Pengelola memori berlapis untuk Agent.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_logger = logging.getLogger(__name__)


@dataclass
class MemoryEntry:
    """Satu entri memori jangka panjang."""

    key: str
    content: str
    category: str  # "rule", "bugfix", "fact", "pattern"
    created_at: str
    relevance_score: float = 1.0


class MemorySystem:
    """Sistem memori 7-layer untuk Agent:
    1. Working Memory: state tugas aktif.
    2. Task Memory: riwayat langkah subtask.
    3. Project Memory: pengetahuan repositori.
    4. Episodic Memory: episik interaksi sebelumnya.
    5. Long-Term Knowledge: fakta, bugfix, dan aturan.
    6. Tool Knowledge: catatan penggunaan tool.
    7. Self Knowledge: kemampuan agent, pola kegagalan tool, strategi sukses, & data debugging.
    """

    def __init__(self, storage_path: Path | None = None) -> None:
        self._storage_path = storage_path or (Path.home() / ".config" / "local-ai-agent" / "memory.json")
        self._working_memory: dict[str, Any] = {}
        self._task_memory: list[dict[str, Any]] = []
        self._long_term_memories: dict[str, MemoryEntry] = {}
        self._project_knowledge: dict[str, Any] = {}
        self._self_knowledge: dict[str, Any] = {
            "tool_failure_patterns": {},
            "successful_strategies": [],
            "debugging_experiences": [],
        }
        self._load_storage()

    # ------------------------------------------------------------------
    # Self Knowledge Layer
    # ------------------------------------------------------------------

    def record_tool_failure(self, tool_name: str, error_pattern: str) -> None:
        """Catat pola kegagalan tool ke Self Knowledge."""
        failures = self._self_knowledge.setdefault("tool_failure_patterns", {})
        failures[tool_name] = failures.get(tool_name, 0) + 1
        self._save_storage()

    def record_successful_strategy(self, task_goal: str, strategy_summary: str) -> None:
        """Catat strategi sukses ke Self Knowledge."""
        strategies = self._self_knowledge.setdefault("successful_strategies", [])
        strategies.append({"goal": task_goal, "strategy": strategy_summary, "timestamp": datetime.now(timezone.utc).isoformat()})
        self._save_storage()

    def get_self_knowledge(self, key: str, default: Any = None) -> Any:
        """Ambil entri dari Self Knowledge."""
        return self._self_knowledge.get(key, default)

    # ------------------------------------------------------------------
    # Short-Term / Working Memory
    # ------------------------------------------------------------------

    def set_working(self, key: str, value: Any) -> None:
        """Simpan data ke Working Memory tugas aktif."""
        self._working_memory[key] = value

    def get_working(self, key: str, default: Any = None) -> Any:
        """Ambil data dari Working Memory."""
        return self._working_memory.get(key, default)

    def clear_working(self) -> None:
        """Kosongkan Working Memory setelah tugas selesai."""
        self._working_memory.clear()

    # ------------------------------------------------------------------
    # Long-Term Memory
    # ------------------------------------------------------------------

    def add_long_term(self, key: str, content: str, category: str = "fact") -> None:
        """Tambah entri ke Long-Term Memory dan simpan ke file."""
        now_iso = datetime.now(timezone.utc).isoformat()
        entry = MemoryEntry(
            key=key,
            content=content,
            category=category,
            created_at=now_iso,
        )
        self._long_term_memories[key] = entry
        self._save_storage()

    def search_long_term(self, query: str, limit: int = 5) -> list[MemoryEntry]:
        """Cari entri Long-Term Memory yang relevan dengan kata kunci query."""
        query_words = set(query.lower().split())
        matched: list[tuple[float, MemoryEntry]] = []

        for entry in self._long_term_memories.values():
            searchable = f"{entry.key} {entry.content} {entry.category}".lower()
            score = sum(1.0 for word in query_words if word in searchable)
            if score > 0:
                matched.append((score, entry))

        matched.sort(key=lambda x: x[0], reverse=True)
        return [entry for _, entry in matched[:limit]]

    # ------------------------------------------------------------------
    # Project Knowledge
    # ------------------------------------------------------------------

    def update_project_knowledge(self, knowledge: dict[str, Any]) -> None:
        """Perbarui pengetahuan tentang struktur dan dependensi proyek."""
        self._project_knowledge.update(knowledge)
        self._save_storage()

    def get_project_knowledge(self) -> dict[str, Any]:
        """Ambil pengetahuan proyek yang tersimpan."""
        return self._project_knowledge

    # ------------------------------------------------------------------
    # Internal Storage (JSON Persistence)
    # ------------------------------------------------------------------

    def _load_storage(self) -> None:
        if not self._storage_path.exists():
            return
        try:
            with open(self._storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            lt_raw = data.get("long_term", {})
            for k, v in lt_raw.items():
                self._long_term_memories[k] = MemoryEntry(
                    key=v.get("key", k),
                    content=v.get("content", ""),
                    category=v.get("category", "fact"),
                    created_at=v.get("created_at", ""),
                )
            self._project_knowledge = data.get("project_knowledge", {})
        except Exception as exc:
            _logger.warning("Gagal membaca storage memori: %s", exc)

    def _save_storage(self) -> None:
        try:
            self._storage_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "long_term": {k: asdict(v) for k, v in self._long_term_memories.items()},
                "project_knowledge": self._project_knowledge,
            }
            with open(self._storage_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as exc:
            _logger.warning("Gagal menyimpan storage memori: %s", exc)


__all__ = ["MemoryEntry", "MemorySystem"]
