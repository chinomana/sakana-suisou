"""Tests for Phase B context indexing and persistence."""

from __future__ import annotations

import json
from pathlib import Path

from fugu_vibe.context import CodebaseIndex, ContextManager, SessionStore


def test_codebase_index_builds_symbols_and_selects_relevant_files(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "alpha.py").write_text("class Alpha:\n    pass\n\ndef helper():\n    pass\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# Project\nAlpha notes\n", encoding="utf-8")
    (tmp_path / ".fugu-vibe").mkdir()
    (tmp_path / ".fugu-vibe" / "ignored.py").write_text("def hidden(): pass\n", encoding="utf-8")

    index = CodebaseIndex(tmp_path)
    data = index.build()

    assert data["count"] == 2
    alpha = next(entry for entry in data["files"] if entry["path"] == "src/alpha.py")
    assert alpha["language"] == "python"
    assert alpha["symbols"] == ["Alpha", "helper"]
    assert index.select_for_context("change Alpha helper")[0]["path"] == "src/alpha.py"


def test_session_store_persists_turns_as_jsonl(tmp_path: Path) -> None:
    store = SessionStore(tmp_path, session_id="test-session")
    user_message = {"role": "user", "content": "hello"}

    store.record_turn(user_message, "world", tool_calls=[{"name": "file_read"}])

    records = store.iter_records()
    assert records[0]["type"] == "turn"
    assert records[0]["payload"]["tool_calls"] == [{"name": "file_read"}]
    assert store.load_messages() == [user_message, {"role": "assistant", "content": "world"}]
    assert json.loads(store.state_path.read_text(encoding="utf-8"))["session_id"] == "test-session"


def test_context_manager_injects_index_overview_and_persists_turn(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("def run():\n    return True\n", encoding="utf-8")
    context = ContextManager(tmp_path)
    user_message = {"role": "user", "content": "update run"}

    messages = context.messages_for(user_message)
    context.add_turn(user_message, "done", tool_calls=[{"name": "git_diff"}])
    summary = context.summary()

    assert any("Codebase overview" in str(message.get("content")) for message in messages)
    assert summary.indexed_files == 1
    assert summary.session_path.exists()
    assert context.session_store.load_messages() == [user_message, {"role": "assistant", "content": "done"}]
