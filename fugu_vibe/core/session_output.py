"""Workspace-backed session output logging."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path


class SessionOutputWriter:
    """Append prompts and responses to a workspace session markdown file."""

    def __init__(self, workspace: Path | None = None):
        root = workspace or Path.cwd()
        session_dir = root / ".fugu-vibe" / "sessions"
        session_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        self.path = session_dir / f"{timestamp}.md"
        self.path.write_text(f"# Fugu Vibe Session {timestamp}\n\n", encoding="utf-8")

    def start_turn(self, prompt: str, attachments: list[Path]) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            f.write("## User\n\n")
            f.write(prompt.rstrip() + "\n\n")
            if attachments:
                f.write("Attachments:\n")
                for path in attachments:
                    f.write(f"- `{path}`\n")
                f.write("\n")
            f.write("## Assistant\n\n")

    def append_response(self, content: str) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            f.write(content)

    def end_turn(self) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            f.write("\n\n")
