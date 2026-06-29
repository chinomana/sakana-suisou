"""Tests for Phase D Fugu-specific optimizations."""

from __future__ import annotations

import pytest

from fugu_vibe.agent.registry import ToolRegistry
from fugu_vibe.api.stream_parser import StreamParser, TokenUsage
from fugu_vibe.config import Config
from fugu_vibe.core.effort import select_effort
from fugu_vibe.core.event_bus import EventBus, EventType
from fugu_vibe.core.instructions import build_instructions, load_instruction_templates
from fugu_vibe.core.orchestration import OrchestrationAnalyzer, OrchestrationPhase
from fugu_vibe.core.token_budget import TokenBudget
from fugu_vibe.tools import FileTools


def test_token_budget_alerts_on_orchestration_ratio_and_budget() -> None:
    budget = TokenBudget(max_total_tokens=1_000, max_orchestration_ratio=0.4, warning_ratio=0.8)

    overhead = budget.check(TokenUsage(input_tokens=100, output_tokens=100, orchestration_tokens=200, total_tokens=400))
    assert overhead is not None
    assert overhead.level == "warning"
    assert "Orchestration overhead" in overhead.message

    exceeded = budget.check(TokenUsage(input_tokens=600, output_tokens=500, orchestration_tokens=0, total_tokens=1_100))
    assert exceeded is not None
    assert exceeded.level == "critical"


def test_instruction_templates_merge_user_and_project(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    user_dir = tmp_path / "user"
    user_dir.mkdir()
    (user_dir / "instructions.md").write_text("Use pytest.", encoding="utf-8")
    (tmp_path / ".fugu").mkdir()
    (tmp_path / ".fugu" / "instructions.md").write_text("Project rules.", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    templates = load_instruction_templates(tmp_path, user_config_dir=user_dir)
    merged = build_instructions("Base", tmp_path, user_config_dir=user_dir)

    assert [template.scope for template in templates] == ["user", "project"]
    assert "Base" in merged
    assert "Use pytest." in merged
    assert "Project rules." in merged


def test_adaptive_effort_selects_low_latency_or_complex_effort() -> None:
    simple = select_effort("explain README.md", "xhigh", adaptive=True)
    complex_task = select_effort(
        "Refactor security orchestration across a.py b.py c.py and update tests",
        "xhigh",
        adaptive=True,
    )

    assert simple.effort == "high"
    assert complex_task.effort == "xhigh"
    assert complex_task.score >= 4


def test_stream_parser_extracts_nested_orchestration_usage_and_stage_signal() -> None:
    parser = StreamParser()
    usage = parser.parse_sse_chunk(
        '{"type":"response.usage.done","usage":{"input_tokens":10,"output_tokens":20,'
        '"details":{"orchestration_tokens":30}}}'
    )
    stage = parser.parse_sse_chunk(
        '{"type":"response.worker.started","worker_id":"W7","message":"worker started"}'
    )

    assert usage is not None
    assert usage.token_usage.total_tokens == 60
    assert usage.token_usage.orchestration_tokens == 30
    assert stage is not None
    assert stage.type == "worker_signal"
    assert stage.worker_id == "W7"


@pytest.mark.asyncio
async def test_orchestration_analyzer_emits_budget_alert(tmp_path) -> None:
    config = Config()
    config.orchestration.token_budget = 100
    config.orchestration.max_orchestration_ratio = 0.2
    bus = EventBus()
    events = []
    bus.on(EventType.STREAM_TOKEN_USAGE, lambda event: events.append(event.data))
    analyzer = OrchestrationAnalyzer(config, bus)

    await analyzer.analyze_chunk(
        type("Chunk", (), {"type": "token_usage", "token_usage": TokenUsage(10, 10, 80, 100), "routing_confidence": None})()
    )
    while bus._queue.qsize():
        await bus._handle_event(await bus._queue.get())

    assert analyzer.state.last_budget_alert is not None
    assert events[-1]["budget_alert"]["level"] == "critical"


@pytest.mark.asyncio
async def test_orchestration_analyzer_uses_explicit_worker_signal() -> None:
    analyzer = OrchestrationAnalyzer(Config())
    chunk = type("Chunk", (), {"type": "worker_signal", "worker_id": "W9", "content": "worker active"})()

    event = await analyzer.analyze_chunk(chunk)

    assert event is not None
    assert event.phase == OrchestrationPhase.WORKER_ACTIVE
    assert analyzer.state.current_worker is not None
    assert analyzer.state.current_worker.worker_id == "W9"


@pytest.mark.asyncio
async def test_registry_returns_structured_tool_errors(tmp_path) -> None:
    registry = ToolRegistry(FileTools(tmp_path))

    result = await registry.dispatch("file_read", {"path": "missing.txt"})

    assert result["ok"] is False
    assert result["error_type"] == "FileToolError"
    assert result["retryable"] is False
    assert result["arguments"] == {"path": "missing.txt"}
