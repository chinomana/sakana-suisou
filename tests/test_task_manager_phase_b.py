"""Tests for Phase B task persistence and recovery."""

from __future__ import annotations

from pathlib import Path

import pytest

from fugu_vibe.config import Config
from fugu_vibe.core.event_bus import EventBus, EventType
from fugu_vibe.core.task_manager import TaskManager, TaskStatus


class FakeClient:
    pass


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
