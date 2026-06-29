"""JSONL conversation history persistence."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4


@dataclass
class SessionStore:
    """Persist complete session turns and events for recovery."""

    workspace: Path
    session_id: str | None = None

    def __post_init__(self) -> None:
        self.workspace = self.workspace.expanduser().resolve()
        if self.session_id == "latest":
            self.session_id = self._latest_session_id()
        self.session_id = self.session_id or datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid4().hex[:8]
        self.session_dir = self.workspace / ".fugu-vibe" / "sessions" / self.session_id
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.history_path = self.session_dir / "history.jsonl"
        self.state_path = self.session_dir / "state.json"
        if not self.history_path.exists():
            self.history_path.touch()
        self.write_state(status="created")

    def append(self, event_type: str, payload: dict[str, Any]) -> None:
        """Append one JSONL event."""
        record = {
            "type": event_type,
            "timestamp": datetime.now().isoformat(),
            "payload": payload,
        }
        with self.history_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def record_turn(
        self,
        user_message: dict[str, Any],
        assistant_content: str,
        tool_calls: list[dict[str, Any]] | None = None,
    ) -> None:
        """Persist a complete user/assistant turn."""
        self.append(
            "turn",
            {
                "user_message": user_message,
                "assistant_message": {"role": "assistant", "content": assistant_content},
                "tool_calls": tool_calls or [],
            },
        )
        self.write_state(status="active")

    def load_messages(self) -> list[dict[str, Any]]:
        """Reconstruct user and assistant messages from persisted turns."""
        messages: list[dict[str, Any]] = []
        for record in self.iter_records():
            if record.get("type") != "turn":
                continue
            payload = record.get("payload", {})
            user_message = payload.get("user_message")
            assistant_message = payload.get("assistant_message")
            if isinstance(user_message, dict):
                messages.append(user_message)
            if isinstance(assistant_message, dict):
                messages.append(assistant_message)
        return messages

    def iter_records(self) -> list[dict[str, Any]]:
        """Load all JSONL records, ignoring malformed lines."""
        records: list[dict[str, Any]] = []
        if not self.history_path.exists():
            return records
        for line in self.history_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(record, dict):
                records.append(record)
        return records

    def write_state(self, status: str, extra: dict[str, Any] | None = None) -> None:
        """Write recoverable session state."""
        data = {
            "session_id": self.session_id,
            "workspace": str(self.workspace),
            "status": status,
            "history_path": str(self.history_path),
            "updated_at": datetime.now().isoformat(),
        }
        if extra:
            data.update(extra)
        tmp_path = self.state_path.with_suffix(".json.tmp")
        tmp_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp_path.replace(self.state_path)

    def _latest_session_id(self) -> str | None:
        sessions_root = self.workspace / ".fugu-vibe" / "sessions"
        if not sessions_root.exists():
            return None
        candidates = [path for path in sessions_root.iterdir() if path.is_dir() and (path / "history.jsonl").exists()]
        if not candidates:
            return None
        return max(candidates, key=lambda path: path.stat().st_mtime).name

