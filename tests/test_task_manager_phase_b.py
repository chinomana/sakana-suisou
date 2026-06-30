"""Tests for Phase B task persistence and recovery."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from fugu_vibe.api.stream_parser import StreamChunk
from fugu_vibe.config import Config
from fugu_vibe.core import task_manager as task_manager_module
from fugu_vibe.core.event_bus import EventBus, EventType
from fugu_vibe.core.task_manager import TaskManager, TaskStatus


class FakeClient:
    pass


class SequencedClient:
    def __init__(self, chunks_by_call: list[list[StreamChunk]]):
        self.chunks_by_call = chunks_by_call
        self.calls: list[dict[str, Any]] = []

    async def send(self, **kwargs: Any):
        self.calls.append(kwargs)
        chunks = self.chunks_by_call.pop(0) if self.chunks_by_call else []
        for chunk in chunks:
            yield chunk


@pytest.fixture
def config() -> Config:
    config = Config()
    config.tasks.use_git_worktree = False
    config.tasks.auto_merge = False
    return config


@pytest.mark.asyncio
async def test_task_manager_persists_stream_output_and_emits_content(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    config: Config,
) -> None:
    monkeypatch.chdir(tmp_path)
    event_bus = EventBus()
    await event_bus.start()
    manager = TaskManager(config, FakeClient(), event_bus, run_scheduler=False)
    await manager.start()
    events: list[str] = []

    event_bus.on(EventType.STREAM_CONTENT, lambda event: events.append(event.data["content"]))
    task = await manager.submit("stream task", prompt="do work")
    task.status = TaskStatus.RUNNING

    manager._append_task_output(task, "hello ")
    await manager._emit(EventType.STREAM_CONTENT, {"task_id": task.task_id, "content": "hello "})
    manager._append_task_output(task, "world")
    await manager._emit(EventType.STREAM_CONTENT, {"task_id": task.task_id, "content": "world"})
    while len(events) < 2:
        await event_bus._handle_event(await event_bus._queue.get())

    reloaded = TaskManager(config, FakeClient(), EventBus(), run_scheduler=False)
    await reloaded.start()
    status = await reloaded.status(task.task_id)

    assert status["output"] == "hello world"
    assert events == ["hello ", "world"]
    await manager.close()
    await reloaded.close()
    await event_bus.close()


@pytest.mark.asyncio
async def test_task_manager_requeues_interrupted_running_task(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    config: Config,
) -> None:
    monkeypatch.chdir(tmp_path)
    manager = TaskManager(config, FakeClient(), EventBus(), run_scheduler=False)
    await manager.start()
    task = await manager.submit("recover task", prompt="do work")
    task.status = TaskStatus.RUNNING
    task.started_at = task.created_at
    manager._persist_task(task)
    await manager.close()

    reloaded = TaskManager(config, FakeClient(), EventBus(), run_scheduler=False)
    await reloaded.start()
    status = await reloaded.status(task.task_id)

    assert status["status"] == "failed"
    assert "Interrupted" in reloaded._tasks[task.task_id].error
    await reloaded.close()


@pytest.mark.asyncio
async def test_task_manager_scheduled_recovery_requeues_running_task(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    config: Config,
) -> None:
    monkeypatch.chdir(tmp_path)
    manager = TaskManager(config, FakeClient(), EventBus(), run_scheduler=False)
    await manager.start()
    task = await manager.submit("resume task", prompt="do work")
    task.status = TaskStatus.RUNNING
    manager._persist_task(task)
    await manager.close()

    reloaded = TaskManager(config, FakeClient(), EventBus(), run_scheduler=False)
    reloaded._run_scheduler = True
    await reloaded.start()

    assert reloaded._tasks[task.task_id].status == TaskStatus.QUEUED
    assert reloaded._queue.qsize() == 1
    await reloaded.close()


@pytest.mark.asyncio
async def test_task_manager_executes_tasks_with_agent_tools(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    config: Config,
) -> None:
    monkeypatch.chdir(tmp_path)
    config.tools.auto_test_after_edit = False
    config.tools.auto_compile_after_edit = False
    config.safety.mode = "auto-edit"

    tool_call = {
        "call_id": "call-1",
        "name": "file_write",
        "arguments": '{"path":"notes.txt","content":"hello from task\\n"}',
    }
    client = SequencedClient(
        [
            [StreamChunk(type="tool_call", tool_call=tool_call)],
            [StreamChunk(type="content", content="done")],
        ]
    )
    manager = TaskManager(config, client, EventBus(), run_scheduler=False)
    await manager.start()
    task = await manager.submit("write file", prompt="write notes")

    await manager._execute_task(task.task_id)

    worktree = Path(manager._tasks[task.task_id].worktree_path)
    assert (worktree / "notes.txt").read_text(encoding="utf-8") == "hello from task\n"
    assert manager._tasks[task.task_id].status == TaskStatus.COMPLETED
    assert manager._tasks[task.task_id].metadata["tool_call_count"] == 1
    assert client.calls[0]["tools"]
    await manager.close()


@pytest.mark.asyncio
async def test_task_manager_scheduler_respects_max_parallel(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    config: Config,
) -> None:
    monkeypatch.chdir(tmp_path)
    config.tasks.max_parallel = 1
    started: list[str] = []
    release = asyncio.Event()

    async def fake_execute(self: TaskManager, task_id: str) -> None:
        self._tasks[task_id].status = TaskStatus.RUNNING
        started.append(task_id)
        await release.wait()
        self._tasks[task_id].status = TaskStatus.COMPLETED

    monkeypatch.setattr(task_manager_module.TaskManager, "_execute_task", fake_execute)
    manager = TaskManager(config, FakeClient(), EventBus(), run_scheduler=False)
    await manager.start()
    first = await manager.submit("one", prompt="one")
    second = await manager.submit("two", prompt="two")

    first_runner = asyncio.create_task(manager._execute_task_with_slot(first.task_id))
    second_runner = asyncio.create_task(manager._execute_task_with_slot(second.task_id))
    await asyncio.sleep(0.05)

    assert started == [first.task_id]
    assert manager._active_task_ids == {first.task_id}

    release.set()
    await asyncio.gather(first_runner, second_runner)

    assert started == [first.task_id, second.task_id]
    assert manager._active_task_ids == set()
    await manager.close()
