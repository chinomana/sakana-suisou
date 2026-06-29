"""Project and user instruction template loading."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class InstructionTemplate:
    """Loaded instruction template content."""

    path: Path
    content: str
    scope: str


def load_instruction_templates(
    workspace: Path,
    *,
    user_config_dir: Path | None = None,
) -> list[InstructionTemplate]:
    """Load user and project instruction templates in priority order."""
    workspace = workspace.expanduser().resolve()
    config_dir = user_config_dir or (Path.home() / ".config" / "fugu-vibe")
    candidates = [
        (config_dir / "instructions.md", "user"),
        (workspace / ".fugu-vibe" / "instructions.md", "project"),
        (workspace / ".fugu" / "instructions.md", "project"),
    ]
    templates: list[InstructionTemplate] = []
    seen: set[Path] = set()
    for path, scope in candidates:
        resolved = path.expanduser().resolve()
        if resolved in seen or not resolved.is_file():
            continue
        seen.add(resolved)
        content = resolved.read_text(encoding="utf-8").strip()
        if content:
            templates.append(InstructionTemplate(path=resolved, content=content, scope=scope))
    return templates


def build_instructions(
    base_instructions: str,
    workspace: Path,
    *,
    user_config_dir: Path | None = None,
) -> str:
    """Merge base coding instructions with user/project templates."""
    sections = [base_instructions.strip()]
    for template in load_instruction_templates(workspace, user_config_dir=user_config_dir):
        sections.append(f"## {template.scope.title()} instructions ({template.path})\n{template.content}")
    return "\n\n".join(section for section in sections if section)
