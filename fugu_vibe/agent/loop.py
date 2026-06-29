"""Minimal Responses function-call execution loop."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from collections.abc import Callable
from typing import Any, Protocol

from fugu_vibe.agent.registry import ToolRegistry
from fugu_vibe.api.stream_parser import StreamChunk
from fugu_vibe.core.event_bus import EventBus, EventType


class StreamingClient(Protocol):
    def send(self, **kwargs: Any): ...


@dataclass
class AgentLoopResult:
    """Final result from one agent turn."""

    content: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    rounds: int = 0


@dataclass
class AgentLoop:
    """Run a model turn, execute local function calls, and continue."""

    client: StreamingClient
    registry: ToolRegistry
    event_bus: EventBus
    max_tool_rounds: int = 4

    async def run(
        self,
        messages: list[dict[str, Any]],
        model: str,
        effort: str,
        web_search: bool = False,
        on_content: Callable[[str], None] | None = None,
        on_tool_call: Callable[[dict[str, Any]], None] | None = None,
    ) -> AgentLoopResult:
        result = AgentLoopResult()
        current_messages = list(messages)

        for round_index in range(self.max_tool_rounds + 1):
            result.rounds = round_index + 1
            content_parts: list[str] = []
            tool_calls: list[dict[str, Any]] = []

            async for chunk in self.client.send(
                messages=current_messages,
                model=model,
                effort=effort,
                web_search=web_search,
                tools=self.registry.schemas(),
            ):
                if chunk.type == "content":
                    content_parts.append(chunk.content)
                    if on_content:
                        on_content(chunk.content)
                    await self.event_bus.emit(
                        EventType.STREAM_CONTENT,
                        {"content": chunk.content},
                        source="agent_loop",
                    )
                elif chunk.type == "tool_call":
                    tool_calls.append(chunk.tool_call)
                    result.tool_calls.append(chunk.tool_call)
                    if on_tool_call:
                        on_tool_call(chunk.tool_call)
                    await self.event_bus.emit(
                        EventType.STREAM_TOOL_CALL,
                        {"tool_call": chunk.tool_call},
                        source="agent_loop",
                    )
                elif chunk.type == "token_usage":
                    await self.event_bus.emit(
                        EventType.STREAM_TOKEN_USAGE,
                        {
                            "input_tokens": chunk.token_usage.input_tokens,
                            "output_tokens": chunk.token_usage.output_tokens,
                            "orchestration_tokens": chunk.token_usage.orchestration_tokens,
                            "total_tokens": chunk.token_usage.total_tokens,
                        },
                        source="agent_loop",
                    )

            content = "".join(content_parts)
            result.content += content
            if not tool_calls:
                return result
            if round_index >= self.max_tool_rounds:
                result.content += "\n[Stopped: maximum tool rounds reached]"
                return result

            if content:
                current_messages.append({"role": "assistant", "content": content})
            for tool_call in tool_calls:
                tool_result = await self.registry.dispatch(
                    str(tool_call.get("name", "")),
                    tool_call.get("arguments", ""),
                )
                current_messages.append(self._tool_result_message(tool_call, tool_result))

        return result

    def _tool_result_message(
        self,
        tool_call: dict[str, Any],
        tool_result: dict[str, Any],
    ) -> dict[str, Any]:
        call_id = tool_call.get("call_id") or tool_call.get("id") or ""
        return {
            "type": "function_call_output",
            "call_id": call_id,
            "output": json.dumps(tool_result, ensure_ascii=False),
        }
