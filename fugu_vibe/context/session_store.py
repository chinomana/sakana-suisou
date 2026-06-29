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
        is_new_session = not self.history_path.exists() and not self.state_path.exists()
        if not self.history_path.exists():
            self.history_path.touch()
        if is_new_session:
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

    def read_state(self) -> dict[str, Any]:
        """Read the latest recoverable session state."""
        if not self.state_path.exists():
            return {}
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}

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

    @classmethod
    def list_sessions(cls, workspace: Path, limit: int = 20) -> list[dict[str, Any]]:
        """Return persisted sessions ordered by most recently updated."""
        workspace = workspace.expanduser().resolve()
        sessions_root = workspace / ".fugu-vibe" / "sessions"
        if not sessions_root.exists():
            return []

        sessions: list[dict[str, Any]] = []
        for path in sessions_root.iterdir():
            if not path.is_dir():
                continue
            history_path = path / "history.jsonl"
            state_path = path / "state.json"
            if not history_path.exists() and not state_path.exists():
                continue
            state: dict[str, Any] = {}
            if state_path.exists():
                try:
                    data = json.loads(state_path.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    data = {}
                if isinstance(data, dict):
                    state = data
            updated_at = str(state.get("updated_at") or datetime.fromtimestamp(path.stat().st_mtime).isoformat())
            turns = state.get("turns")
            if not isinstance(turns, int):
                turns = cls._count_turns(history_path)
            sessions.append(
                {
                    "session_id": path.name,
                    "status": state.get("status", "unknown"),
                    "turns": turns,
                    "attachments": len(state.get("attachments", [])) if isinstance(state.get("attachments"), list) else 0,
                    "updated_at": updated_at,
                    "path": str(path),
                }
            )
        return sorted(sessions, key=lambda item: str(item.get("updated_at", "")), reverse=True)[:limit]

    @staticmethod
    def _count_turns(history_path: Path) -> int:
        if not history_path.exists():
            return 0
        count = 0
        for line in history_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(record, dict) and record.get("type") == "turn":
                count += 1
        return count

    def _latest_session_id(self) -> str | None:
        sessions_root = self.workspace / ".fugu-vibe" / "sessions"
        if not sessions_root.exists():
            return None
        candidates = [path for path in sessions_root.iterdir() if path.is_dir() and (path / "history.jsonl").exists()]
        if not candidates:
            return None
        return max(candidates, key=lambda path: path.stat().st_mtime).name

