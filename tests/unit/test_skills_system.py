"""Tests for Autonomous Skill System."""
import pytest
from pathlib import Path
from agent.skills.skill import Skill
from agent.skills.manager import SkillManager
from agent.skills.creator import SkillCreator
from agent.models.schemas import ToolResult


def test_skill_markdown_roundtrip(tmp_path: Path):
    md_content = """# Skill: Deployment

> Panduan otomatis deploy ke server produksi.

**Triggers**: deploy, release, production

## Panduan & Petunjuk Langkah:
1. Jalankan test suite
2. Build binary
3. Deploy ke server

## Contoh Penggunaan:
- tolong deploy kode terbaru
"""
    skill = Skill.from_markdown(md_content)
    assert skill.name == "Deployment"
    assert "deploy" in skill.triggers
    assert "Jalankan test suite" in skill.instructions
    assert skill.matches("tolong deploy sekarang") is True

    exported_md = skill.to_markdown()
    assert "# Skill: Deployment" in exported_md
    assert "deploy, release, production" in exported_md


def test_skill_manager_discovery_and_matching(tmp_path: Path):
    skill_dir = tmp_path / "skills"
    skill_dir.mkdir()
    skill_file = skill_dir / "git_helper.md"
    skill_file.write_text("""# Skill: Git Helper

> Bantuan perintah git.

**Triggers**: git, commit, push

## Panduan & Petunjuk Langkah:
Gunakan git status lalu git commit.
""", encoding="utf-8")

    manager = SkillManager(skill_dirs=[skill_dir])
    skills = manager.list_skills()
    assert len(skills) >= 1
    assert manager.get_skill("Git Helper") is not None

    matched = manager.match_skills("tolong cek git commit")
    assert len(matched) == 1
    assert matched[0].name == "Git Helper"

    context = manager.format_skills_context("cek status git")
    assert "Git Helper" in context


def test_skill_creator(tmp_path: Path):
    manager = SkillManager(skill_dirs=[tmp_path])
    creator = SkillCreator(skill_manager=manager, output_dir=tmp_path)

    results = [ToolResult(success=True, data={"out": "ok"}, tool_name="shell")]
    created_skill = creator.create_skill_from_task(
        task_name="Backup Database",
        goal="backup database SQLite ke folder backup",
        steps=["Jalankan copy database", "Verifikasi file backup"],
        tool_results=results,
        triggers=["backup", "database"],
    )

    assert created_skill.name == "Backup Database"
    assert "shell" in created_skill.instructions
    assert manager.get_skill("Backup Database") is not None
    assert (tmp_path / "backup_database.md").exists()
