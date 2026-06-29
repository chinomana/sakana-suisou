"""Tests for Phase E dashboard, headless, and MCP integration."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

from fugu_vibe.agent import ToolRegistry
from fugu_vibe.api.stream_parser import StreamChunk
from fugu_vibe.config import Config
from fugu_vibe.core.event_bus import Event, EventType
from fugu_vibe.core.headless import run_headless
from fugu_vibe.mcp import MCPClient, MCPConfigStore, MCPServer, MCPToolManager
from fugu_vibe.tools import FileTools
from fugu_vibe.ui.components import TokenMeter
from fugu_vibe.ui.dashboard import OrchestrationDashboard


class FakeStreamingClient:
    def __init__(self, chunks: list[StreamChunk]):
        self.chunks = chunks

    async def send(self, **kwargs: Any):
        for chunk in self.chunks:
            yield chunk


@pytest.mark.asyncio
async def test_run_headless_returns_structured_result(tmp_path: Path) -> None:
    client = FakeStreamingClient([StreamChunk(type="content", content="done")])

    result = await run_headless("say done", Config(), workspace=tmp_path, client=client, log_events=False)

    assert result.ok is True
    assert result.content == "done"
    assert result.rounds == 1
    assert result.to_dict()["effort"] in {"high", "xhigh"}


def test_token_meter_tracks_cost_and_budget_alert() -> None:
    meter = TokenMeter()
    alert = {"level": "critical", "message": "Budget exceeded", "estimated_cost_usd": 1.25}

    meter.update(10, 20, 30, estimated_cost_usd=1.25, budget_alert=alert)
    rendered = meter.render()

    assert meter.estimated_cost_usd == 1.25
    assert meter.budget_alert == alert
    assert rendered.row_count >= 6


def test_dashboard_handles_budget_alert_event() -> None:
    dashboard = OrchestrationDashboard(Config(), event_bus=None)  # type: ignore[arg-type]
    alert = {"level": "warning", "message": "Orchestration overhead high"}

    dashboard._on_stream_token_usage(
        Event(
            EventType.STREAM_TOKEN_USAGE,
            {"input_tokens": 1, "output_tokens": 2, "orchestration_tokens": 3, "budget_alert": alert},
        )
    )

    assert dashboard.token_meter.orchestration_tokens == 3
    assert dashboard.token_meter.budget_alert == alert
    assert dashboard._last_budget_alert == alert


def test_mcp_config_store_round_trips_servers(tmp_path: Path) -> None:
    store = MCPConfigStore(tmp_path)
    store.add(MCPServer("demo", sys.executable, ["server.py"], {"A": "B"}))

    server = store.get("demo")

    assert server is not None
    assert server.command == sys.executable
    assert server.args == ["server.py"]
    assert server.env == {"A": "B"}
    assert store.remove("demo") is True
    assert store.list_servers() == []


def test_registry_exposes_mcp_bridge_tools(tmp_path: Path) -> None:
    registry = ToolRegistry(FileTools(tmp_path), mcp_tools=MCPToolManager(MCPConfigStore(tmp_path)))

    names = {schema["name"] for schema in registry.schemas()}

    assert {"mcp_list_tools", "mcp_call"} <= names


@pytest.mark.asyncio
async def test_mcp_client_lists_and_calls_stdio_server(tmp_path: Path) -> None:
    server_script = tmp_path / "mcp_server.py"
    server_script.write_text(
        """
import json
import sys

for line in sys.stdin:
    message = json.loads(line)
    if "id" not in message:
        continue
    method = message.get("method")
    if method == "initialize":
        result = {"protocolVersion": "2024-11-05", "capabilities": {}}
    elif method == "tools/list":
        result = {"tools": [{"name": "echo", "description": "Echo text", "inputSchema": {"type": "object"}}]}
    elif method == "tools/call":
        args = message.get("params", {}).get("arguments", {})
        result = {"content": [{"type": "text", "text": args.get("text", "")}]}
    else:
        result = {}
    sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": message["id"], "result": result}) + "\\n")
    sys.stdout.flush()
""".strip(),
        encoding="utf-8",
    )

    async with MCPClient(MCPServer("demo", sys.executable, [str(server_script)])) as client:
        tools = await client.list_tools()
        result = await client.call_tool("echo", {"text": "hello"})

    assert tools[0].name == "echo"
    assert result["content"][0]["text"] == "hello"
