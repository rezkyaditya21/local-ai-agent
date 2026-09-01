"""
agent/skills/skill.py

Model data untuk representasi Skill otonom (kompatibel dengan agentskills.io dan format markdown).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Skill:
    """Representasi satu skill kemampuan agen."""

    name: str
    description: str
    instructions: str
    triggers: list[str] = field(default_factory=list)
    examples: list[str] = field(default_factory=list)
    file_path: Path | None = None
    enabled: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def matches(self, query: str) -> bool:
        """Cek apakah query memicu aktivasi skill ini."""
        query_lower = query.lower()
        if self.name.lower() in query_lower:
            return True
        for trigger in self.triggers:
            if trigger.lower() in query_lower:
                return True
        return False

    def to_markdown(self) -> str:
        """Konversi skill ke format Markdown terstruktur."""
        triggers_str = ", ".join(self.triggers)
        examples_str = "\n".join(f"- {ex}" for ex in self.examples) if self.examples else "- (tidak ada contoh spesifik)"
        return f"""# Skill: {self.name}

> {self.description}

**Triggers**: {triggers_str}

## Panduan & Petunjuk Langkah:
{self.instructions.strip()}

## Contoh Penggunaan:
{examples_str}
"""

    @classmethod
    def from_markdown(cls, content: str, file_path: Path | None = None) -> Skill:
        """Parse skill dari teks Markdown."""
        lines = content.strip().splitlines()
        name = file_path.stem if file_path else "unnamed_skill"
        description = ""
        triggers: list[str] = []
        examples: list[str] = []
        instructions_lines: list[str] = []

        current_section = "header"

        for line in lines:
            trimmed = line.strip()
            if trimmed.startswith("# Skill:"):
                name = trimmed.replace("# Skill:", "").strip()
            elif trimmed.startswith(">") and current_section == "header":
                description = trimmed.lstrip("> ").strip()
            elif trimmed.startswith("**Triggers**:") or trimmed.startswith("Triggers:"):
                raw_trig = trimmed.split(":", 1)[1].strip()
                triggers = [t.strip() for t in raw_trig.split(",") if t.strip()]
            elif trimmed.startswith("## Panduan") or trimmed.startswith("## Instructions") or trimmed.startswith("## Steps"):
                current_section = "instructions"
            elif trimmed.startswith("## Contoh") or trimmed.startswith("## Examples"):
                current_section = "examples"
            elif trimmed.startswith("##"):
                current_section = "other"
            else:
                if current_section == "instructions":
                    instructions_lines.append(line)
                elif current_section == "examples" and trimmed.startswith("-"):
                    examples.append(trimmed.lstrip("- ").strip())

        instructions = "\n".join(instructions_lines).strip()
        if not description and instructions:
            description = instructions.splitlines()[0][:100]

        return cls(
            name=name,
            description=description,
            instructions=instructions,
            triggers=triggers,
            examples=examples,
            file_path=file_path,
        )


__all__ = ["Skill"]
