"""Agent Skills loader.

Each folder in ``skills/`` follows the open Agent Skills format (agentskills.io):
a ``SKILL.md`` with YAML front matter (``name``, ``description``) and Markdown
instructions. Descriptions are always visible to the agent; a skill's full body
is loaded only when a task needs it, which keeps prompts small and cheap.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

SKILLS_DIR = Path(__file__).resolve().parent / "skills"


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    body: str
    path: str


def _parse(path: Path) -> Skill:
    text = path.read_text(encoding="utf-8")
    meta: dict[str, str] = {}
    body = text
    if text.startswith("---"):
        _, fm, body = text.split("---", 2)
        for line in fm.strip().splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip()
    return Skill(meta.get("name", path.parent.name), meta.get("description", ""), body.strip(),
                 str(path.relative_to(SKILLS_DIR.parent.parent.parent)))


@lru_cache
def load_skills() -> dict[str, Skill]:
    return {s.name: s for s in (_parse(p) for p in sorted(SKILLS_DIR.glob("*/SKILL.md")))}


def skill_prompt(*names: str) -> str:
    """System-prompt text for the given skills (full bodies)."""
    skills = load_skills()
    return "\n\n".join(f"## Skill: {n}\n{skills[n].body}" for n in names if n in skills)


def skill_catalog() -> list[dict]:
    return [{"name": s.name, "description": s.description, "path": s.path} for s in load_skills().values()]
