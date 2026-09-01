"""
agent/skills/creator.py

SkillCreator — mengekstrak dan membuat skill baru secara mandiri
berdasarkan pengalaman dan keberhasilan penyelesaian tugas oleh agen.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from agent.models.schemas import ToolResult
from agent.skills.manager import SkillManager
from agent.skills.skill import Skill

_logger = logging.getLogger(__name__)


class SkillCreator:
    """Pembuat skill otonom yang menyusun pengalaman sukses menjadi format skill standar."""

    def __init__(self, skill_manager: SkillManager, output_dir: Path | None = None) -> None:
        self._skill_manager = skill_manager
        self._output_dir = output_dir or Path("./skills")

    def create_skill_from_task(
        self,
        task_name: str,
        goal: str,
        steps: list[str],
        tool_results: list[ToolResult] | None = None,
        triggers: list[str] | None = None,
    ) -> Skill:
        """Buat skill baru dari data riwayat penyelesaian tugas."""
        instructions_parts = []
        if steps:
            for idx, step in enumerate(steps, 1):
                instructions_parts.append(f"{idx}. {step}")
        else:
            instructions_parts.append(f"1. Analisis tujuan: {goal}")
            instructions_parts.append("2. Gunakan tool yang sesuai secara berurutan.")
            instructions_parts.append("3. Verifikasi hasil akhir sebelum selesai.")

        if tool_results:
            tools_used = sorted(list({r.tool_name for r in tool_results if r.success}))
            if tools_used:
                instructions_parts.append(f"\nTool yang direkomendasikan: {', '.join(tools_used)}")

        clean_triggers = triggers or [t.strip() for t in goal.lower().split() if len(t) > 3][:4]
        if not clean_triggers:
            clean_triggers = [task_name.lower()]

        description = f"Panduan otonom untuk menyelesaikan: {goal}"
        skill = Skill(
            name=task_name,
            description=description,
            instructions="\n".join(instructions_parts),
            triggers=clean_triggers,
            examples=[goal],
        )

        # Simpan dan daftarkan ke manager
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._skill_manager.register_skill(skill, save_to_dir=self._output_dir)
        _logger.info("Skill baru berhasil dibuat dan disimpan: %s", skill.name)
        return skill

    def create_skill_from_markdown(self, markdown_text: str, name: str | None = None) -> Skill:
        """Buat skill baru langsung dari teks Markdown."""
        skill = Skill.from_markdown(markdown_text)
        if name:
            skill.name = name
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._skill_manager.register_skill(skill, save_to_dir=self._output_dir)
        return skill


__all__ = ["SkillCreator"]
