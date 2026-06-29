"""Workspace-backed context tracking for interactive sessions."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class ContextSummary:
    """A small summary of the current prompt context."""

    history_messages: int
    turns: int
    attachments: list[dict[str, Any]]
    compacted: bool
    compact_summary_chars: int
    metadata_path: Path


@dataclass
class ContextManager:
    """Track conversation history, attachments, and compacted context."""

    workspace: Path = field(default_factory=Path.cwd)
    history: list[dict[str, Any]] = field(default_factory=list)
    attachments: list[Path] = field(default_factory=list)
    tool_usage: list[dict[str, Any]] = field(default_factory=list)
    compact_summary: str = ""

    def __post_init__(self) -> None:
        self.workspace = self.workspace.expanduser().resolve()
        self.metadata_path = self.workspace / ".fugu-vibe" / "context" / "current.json"
        self.metadata_path.parent.mkdir(parents=True, exist_ok=True)
        self.persist()

    def add_attachment(self, path: Path) -> Path:
        resolved = path.expanduser().resolve()
        if not resolved.is_file():
            raise FileNotFoundError(f"Not a file: {path}")
        if resolved not in self.attachments:
            self.attachments.append(resolved)
            self.persist()
        return resolved

    def clear_attachments(self) -> None:
        self.attachments.clear()
        self.persist()

    def add_turn(self, user_message: dict[str, Any], assistant_content: str) -> None:
        self.history.append(user_message)
        self.history.append({"role": "assistant", "content": assistant_content})
        self.persist()

    def messages_for(self, user_message: dict[str, Any]) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []
        if self.compact_summary:
            messages.append(
                {
                    "role": "user",
                    "content": "Conversation summary so far:\n" + self.compact_summary,
                }
            )
        messages.extend(self.history)
        messages.append(user_message)
        return messages

    def compact(self, keep_recent_turns: int = 3) -> str:
        """Compact older turns into a local summary and keep recent turns verbatim."""
        keep_messages = keep_recent_turns * 2
        if len(self.history) <= keep_messages:
            return "Nothing to compact; history is already short."

        old_messages = self.history[:-keep_messages]
        self.history = self.history[-keep_messages:]
        lines = []
        if self.compact_summary:
            lines.append(self.compact_summary.rstrip())
            lines.append("")
        lines.append(f"Compacted {len(old_messages) // 2} earlier turn(s) at {datetime.now().isoformat()}.")
        for message in old_messages:
            role = message.get("role", "unknown")
            content = message.get("content", "")
            lines.append(f"- {role}: {self._preview_content(content)}")
        self.compact_summary = "\n".join(lines).strip()
        self.persist()
        return f"Compacted {len(old_messages) // 2} turn(s). Kept {keep_recent_turns} recent turn(s)."

    def summary(self) -> ContextSummary:
        return ContextSummary(
            history_messages=len(self.history),
            turns=len(self.history) // 2,
            attachments=[self._attachment_info(path) for path in self.attachments],
            compacted=bool(self.compact_summary),
            compact_summary_chars=len(self.compact_summary),
            metadata_path=self.metadata_path,
        )

    def record_tool_usage(self, name: str, arguments: dict[str, Any], result_count: int | None = None) -> None:
        self.tool_usage.append(
            {
                "name": name,
                "arguments": arguments,
                "result_count": result_count,
                "timestamp": datetime.now().isoformat(),
            }
        )
        self.tool_usage = self.tool_usage[-50:]
        self.persist()

    def persist(self) -> None:
        data = {
            "workspace": str(self.workspace),
            "history_messages": len(self.history),
            "turns": len(self.history) // 2,
            "attachments": [self._attachment_info(path) for path in self.attachments],
            "tool_usage": self.tool_usage,
            "compacted": bool(self.compact_summary),
            "compact_summary": self.compact_summary,
            "updated_at": datetime.now().isoformat(),
        }
        tmp_path = self.metadata_path.with_suffix(".json.tmp")
        tmp_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp_path.replace(self.metadata_path)

    def _attachment_info(self, path: Path) -> dict[str, Any]:
        try:
            size = path.stat().st_size
        except OSError:
            size = None
        return {"path": str(path), "name": path.name, "size_bytes": size}

    def _preview_content(self, content: Any, limit: int = 300) -> str:
        if isinstance(content, list):
            text_parts = []
            for part in content:
                if isinstance(part, dict) and part.get("type") == "input_text":
                    text_parts.append(str(part.get("text", "")))
                elif isinstance(part, dict):
                    text_parts.append(f"[{part.get('type', 'part')}]")
            text = " ".join(text_parts)
        else:
            text = str(content)
        text = " ".join(text.split())
        if len(text) > limit:
            return text[: limit - 3] + "..."
        return text
