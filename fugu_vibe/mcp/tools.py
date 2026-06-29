"""Generic local tools that bridge Fugu to configured MCP servers."""

from __future__ import annotations

from typing import Any

from fugu_vibe.mcp.client import MCPClient, MCPError
from fugu_vibe.mcp.store import MCPConfigStore


class MCPToolManager:
    """Expose configured MCP servers as lazy generic function tools."""

    def __init__(self, store: MCPConfigStore, *, timeout_seconds: float = 30.0):
        self.store = store
        self.timeout_seconds = timeout_seconds

    def schemas(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "name": "mcp_list_tools",
                "description": "List tools from configured MCP servers. Use before mcp_call. Read-only.",
                "parameters": {
                    "type": "object",
                    "properties": {"server": {"type": "string", "default": ""}},
                },
            },
            {
                "type": "function",
                "name": "mcp_call",
                "description": "Call a tool on a configured MCP server with JSON arguments.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "server": {"type": "string"},
                        "tool": {"type": "string"},
                        "arguments": {"type": "object", "default": {}},
                    },
                    "required": ["server", "tool"],
                },
            },
        ]

    async def list_tools(self, server_name: str | None = None) -> dict[str, Any]:
        servers = [self.store.get(server_name)] if server_name else self.store.list_servers()
        servers = [server for server in servers if server is not None]
        tools: list[dict[str, Any]] = []
        errors: list[dict[str, str]] = []
        for server in servers:
            try:
                async with MCPClient(server, timeout_seconds=self.timeout_seconds) as client:
                    for tool in await client.list_tools():
                        tools.append(
                            {
                                "server": tool.server,
                                "name": tool.name,
                                "description": tool.description,
                                "input_schema": tool.input_schema,
                            }
                        )
            except (OSError, MCPError, TimeoutError) as exc:
                errors.append({"server": server.name, "error": str(exc)})
        return {"tools": tools, "errors": errors, "server_count": len(servers)}

    async def call_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        server = self.store.get(server_name)
        if server is None:
            return {"ok": False, "error": f"Unknown MCP server: {server_name}", "retryable": False}
        try:
            async with MCPClient(server, timeout_seconds=self.timeout_seconds) as client:
                result = await client.call_tool(tool_name, arguments or {})
        except (OSError, MCPError, TimeoutError) as exc:
            return {"ok": False, "error": str(exc), "retryable": isinstance(exc, TimeoutError)}
        return {"ok": True, "server": server_name, "tool": tool_name, "result": result}
