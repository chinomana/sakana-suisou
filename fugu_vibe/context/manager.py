"""Workspace-backed context tracking for interactive sessions."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from fugu_vibe.context.index import CodebaseIndex
from fugu_vibe.context.session_store import SessionStore
from fugu_vibe.core.attachments import MAX_INLINE_TEXT_BYTES, TEXT_EXTENSIONS


@dataclass
class ContextSummary:
    """A small summary of the current prompt context."""

    history_messages: int
    turns: int
    attachments: list[dict[str, Any]]
    compacted: bool
    compact_summary_chars: int
    metadata_path: Path
    session_id: str
    session_path: Path
    index_path: Path
    indexed_files: int
    index_truncated: bool


@dataclass
class ContextManager:
    """Track conversation history, attachments, and compacted context."""

    workspace: Path = field(default_factory=Path.cwd)
    session_id: str | None = None
    history: list[dict[str, Any]] = field(default_factory=list)
    attachments: list[Path] = field(default_factory=list)
    tool_usage: list[dict[str, Any]] = field(default_factory=list)
    compact_summary: str = ""
    index: CodebaseIndex = field(init=False)
    session_store: SessionStore = field(init=False)

    def __post_init__(self) -> None:
        self.workspace = self.workspace.expanduser().resolve()
        self.metadata_path = self.workspace / ".fugu-vibe" / "context" / "current.json"
        self.metadata_path.parent.mkdir(parents=True, exist_ok=True)
        self.index = CodebaseIndex(self.workspace)
        self.index.load_or_build()
        self.session_store = SessionStore(self.workspace, session_id=self.session_id)
        self.session_id = self.session_store.session_id
        self._restore_state()
        if self.session_store.history_path.stat().st_size > 0 and not self.history:
            self.history = self.session_store.load_messages()
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

    def add_turn(
        self,
        user_message: dict[str, Any],
        assistant_content: str,
        tool_calls: list[dict[str, Any]] | None = None,
    ) -> None:
        assistant_message = {"role": "assistant", "content": assistant_content}
        self.history.append(user_message)
        self.history.append(assistant_message)
        self.session_store.record_turn(user_message, assistant_content, tool_calls=tool_calls)
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
        if self.index.files:
            messages.append(
                {
                    "role": "user",
                    "content": "Codebase overview for routing and context selection:\n" + self.index.overview(),
                }
            )
        snippets = self.context_snippets_for(user_message)
        if snippets:
            messages.append(
                {
                    "role": "user",
                    "content": "Selected workspace context for the current request:\n" + snippets,
                }
            )
        messages.extend(self.history)
        messages.append(user_message)
        return messages

    def context_snippets_for(
        self,
        user_message: dict[str, Any] | str,
        *,
        max_files: int = 5,
        max_chars_per_file: int = 4_000,
    ) -> str:
        """Return compact file snippets selected for the current request."""
        query = self._message_text(user_message)
        selected = self.select_context_files(query, max_files=max_files)
        snippets: list[str] = []
        for entry in selected:
            relative_path = str(entry.get("path", ""))
            if not relative_path:
                continue
            path = (self.workspace / relative_path).resolve()
            if not self._can_inline_context_file(path):
                continue
            try:
                content = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if len(content) > max_chars_per_file:
                content = content[: max_chars_per_file - 32].rstrip() + "\n... [truncated]"
            language = str(entry.get("language", "text"))
            snippets.append(f"File: {relative_path}\n```{language}\n{content}\n```")
        return "\n\n".join(snippets)

    def rebuild_index(self) -> dict[str, Any]:
        """Refresh the workspace codebase index."""
        data = self.index.build()
        self.persist()
        return data

    def select_context_files(self, query: str, max_files: int = 10) -> list[dict[str, Any]]:
        """Select likely relevant files from the codebase index."""
        return self.index.select_for_context(query, max_files=max_files)

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
            session_id=str(self.session_store.session_id),
            session_path=self.session_store.history_path,
            index_path=self.index.cache_path or self.workspace / ".fugu-vibe" / "index.json",
            indexed_files=len(self.index.files),
            index_truncated=self.index.truncated,
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
        data = self._state_snapshot()
        tmp_path = self.metadata_path.with_suffix(".json.tmp")
        tmp_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp_path.replace(self.metadata_path)
        self.session_store.write_state(status="active", extra=data)

    def _state_snapshot(self) -> dict[str, Any]:
        return {
            "workspace": str(self.workspace),
            "history_messages": len(self.history),
            "turns": len(self.history) // 2,
            "attachments": [self._attachment_info(path) for path in self.attachments],
            "tool_usage": self.tool_usage,
            "compacted": bool(self.compact_summary),
            "compact_summary": self.compact_summary,
            "session_id": self.session_store.session_id,
            "session_path": str(self.session_store.history_path),
            "index_path": str(self.index.cache_path),
            "indexed_files": len(self.index.files),
            "index_truncated": self.index.truncated,
            "updated_at": datetime.now().isoformat(),
        }

    def _restore_state(self) -> None:
        state = self.session_store.read_state()
        self.compact_summary = str(state.get("compact_summary") or self.compact_summary)
        tool_usage = state.get("tool_usage")
        if isinstance(tool_usage, list):
            self.tool_usage = [entry for entry in tool_usage if isinstance(entry, dict)][-50:]

        attachments = state.get("attachments")
        if isinstance(attachments, list):
            restored: list[Path] = []
            for item in attachments:
                raw_path = item.get("path") if isinstance(item, dict) else item
                if not raw_path:
                    continue
                path = Path(str(raw_path)).expanduser()
                if not path.is_absolute():
                    path = self.workspace / path
                try:
                    resolved = path.resolve()
                except OSError:
                    continue
                if resolved.is_file() and resolved not in restored:
                    restored.append(resolved)
            self.attachments = restored

    def _can_inline_context_file(self, path: Path) -> bool:
        try:
            resolved = path.resolve()
            resolved.relative_to(self.workspace)
            stat = resolved.stat()
        except (OSError, ValueError):
            return False
        if stat.st_size > MAX_INLINE_TEXT_BYTES:
            return False
        return resolved.suffix.lower() in TEXT_EXTENSIONS

    def _message_text(self, message: dict[str, Any] | str) -> str:
        if isinstance(message, str):
            return message
        content = message.get("content", "")
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "input_text":
                    parts.append(str(item.get("text", "")))
            return " ".join(parts)
        return str(content)

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
