"""
agent/skills/manager.py

SkillManager — menemukan, mengelola, dan menyuntikkan skill ke prompt agen.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from agent.skills.skill import Skill

_logger = logging.getLogger(__name__)


class SkillManager:
    """Pengelola katalog skill agen lokal.

    Mendukung penemuan otomatis dari:
    1. Direktori proyek lokal (`./skills/`)
    2. Direktori konfigurasi global (`~/.config/local-ai-agent/skills/`)
    """

    def __init__(self, skill_dirs: list[Path] | None = None) -> None:
        if skill_dirs is None:
            self._skill_dirs = [
                Path("./skills"),
                Path.home() / ".config" / "local-ai-agent" / "skills",
            ]
        else:
            self._skill_dirs = skill_dirs

        self._skills: dict[str, Skill] = {}
        self.discover_skills()

    def discover_skills(self) -> int:
        """Pindai direktori skill dan muat semua berkas .md."""
        loaded = 0
        for s_dir in self._skill_dirs:
            if not s_dir.exists():
                continue
            for file_path in s_dir.glob("*.md"):
                try:
                    content = file_path.read_text(encoding="utf-8")
                    skill = Skill.from_markdown(content, file_path=file_path)
                    self._skills[skill.name.lower()] = skill
                    loaded += 1
                except Exception as exc:
                    _logger.warning("Gagal memuat skill dari %s: %s", file_path, exc)
        return loaded

    def register_skill(self, skill: Skill, save_to_dir: Path | None = None) -> Path | None:
        """Daftarkan skill baru ke memori dan opsional simpan ke disk."""
        self._skills[skill.name.lower()] = skill
        if save_to_dir or self._skill_dirs:
            target_dir = save_to_dir or self._skill_dirs[0]
            target_dir.mkdir(parents=True, exist_ok=True)
            safe_name = skill.name.lower().replace(" ", "_").replace("/", "_") + ".md"
            target_file = target_dir / safe_name
            target_file.write_text(skill.to_markdown(), encoding="utf-8")
            skill.file_path = target_file
            return target_file
        return None

    def get_skill(self, name: str) -> Skill | None:
        """Ambil skill berdasarkan nama."""
        return self._skills.get(name.lower())

    def list_skills(self) -> list[Skill]:
        """Daftar semua skill yang tersedia."""
        return list(self._skills.values())

    def match_skills(self, query: str, max_matches: int = 3) -> list[Skill]:
        """Cari skill yang relevan dengan instruksi pengguna."""
        matches: list[Skill] = []
        for skill in self._skills.values():
            if not skill.enabled:
                continue
            if skill.matches(query):
                matches.append(skill)
                if len(matches) >= max_matches:
                    break
        return matches

    def format_skills_context(self, query: str) -> str:
        """Format skill yang cocok sebagai teks konteks untuk disuntikkan ke prompt."""
        matched = self.match_skills(query)
        if not matched:
            return ""

        parts = ["--- Skill Relevan Terdeteksi ---"]
        for s in matched:
            parts.append(f"### Skill: {s.name}")
            parts.append(f"Deskripsi: {s.description}")
            if s.instructions:
                parts.append(f"Langkah Pengerjaan:\n{s.instructions}")
            parts.append("")
        return "\n".join(parts).strip()

    def format_skills_catalog(self) -> str:
        """Format ringkasan semua skill yang terdaftar."""
        if not self._skills:
            return "(belum ada skill tambahan yang terpasang)"
        lines = []
        for s in self._skills.values():
            status = "aktif" if s.enabled else "nonaktif"
            lines.append(f"- **{s.name}** ({status}): {s.description}")
        return "\n".join(lines)


__all__ = ["SkillManager"]
