"""Minimal stdio MCP client for tool discovery and invocation."""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass, field
from typing import Any


class MCPError(Exception):
    """Raised when an MCP server request fails."""


@dataclass(frozen=True)
class MCPServer:
    """Configuration for one stdio MCP server."""

    name: str
    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class MCPTool:
    """Tool advertised by an MCP server."""

    server: str
    name: str
    description: str = ""
    input_schema: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, server: str, payload: dict[str, Any]) -> MCPTool:
        return cls(
            server=server,
            name=str(payload.get("name", "")),
            description=str(payload.get("description", "")),
            input_schema=payload.get("inputSchema")
            if isinstance(payload.get("inputSchema"), dict)
            else {},
        )


class MCPClient:
    """JSON-RPC over stdio MCP client."""

    def __init__(self, server: MCPServer, *, timeout_seconds: float = 30.0):
        self.server = server
        self.timeout_seconds = timeout_seconds
        self._process: asyncio.subprocess.Process | None = None
        self._next_id = 1

    async def __aenter__(self) -> MCPClient:
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    async def start(self) -> None:
        """Start and initialize the MCP server process."""
        if self._process is not None:
            return
        self._process = await asyncio.create_subprocess_exec(
            self.server.command,
            *self.server.args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=self._process_env(),
        )
        await self._request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "fugu-vibe-cli", "version": "0.1.0"},
            },
        )
        await self._notify("notifications/initialized", {})

    async def close(self) -> None:
        """Terminate the MCP server process."""
        process = self._process
        self._process = None
        if process is None:
            return
        if process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=3)
            except TimeoutError:
                process.kill()
                await process.wait()

    async def list_tools(self) -> list[MCPTool]:
        """Return tools exposed by the server."""
        payload = await self._request("tools/list", {})
        tools = payload.get("tools", [])
        if not isinstance(tools, list):
            raise MCPError("MCP tools/list returned an invalid tools payload")
        return [MCPTool.from_payload(self.server.name, tool) for tool in tools if isinstance(tool, dict)]

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        """Invoke an MCP tool and return the raw result payload."""
        return await self._request("tools/call", {"name": name, "arguments": arguments or {}})

    async def _request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        process = self._require_process()
        request_id = self._next_id
        self._next_id += 1
        payload = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
        await self._write_json(payload)
        while True:
            if process.stdout is None:
                raise MCPError("MCP server stdout is not available")
            line = await asyncio.wait_for(process.stdout.readline(), timeout=self.timeout_seconds)
            if not line:
                stderr = await self._read_stderr_tail(process)
                raise MCPError(f"MCP server exited while waiting for {method}: {stderr}".strip())
            response = json.loads(line.decode("utf-8"))
            if response.get("id") != request_id:
                continue
            if "error" in response:
                raise MCPError(str(response["error"]))
            result = response.get("result", {})
            if not isinstance(result, dict):
                raise MCPError(f"MCP {method} returned a non-object result")
            return result

    async def _notify(self, method: str, params: dict[str, Any]) -> None:
        await self._write_json({"jsonrpc": "2.0", "method": method, "params": params})

    async def _write_json(self, payload: dict[str, Any]) -> None:
        process = self._require_process()
        if process.stdin is None:
            raise MCPError("MCP server stdin is not available")
        process.stdin.write(json.dumps(payload, separators=(",", ":")).encode("utf-8") + b"\n")
        await process.stdin.drain()

    def _require_process(self) -> asyncio.subprocess.Process:
        if self._process is None:
            raise MCPError("MCP server is not running")
        return self._process

    def _process_env(self) -> dict[str, str] | None:
        if not self.server.env:
            return None
        return {**os.environ, **self.server.env}


    async def _read_stderr_tail(self, process: asyncio.subprocess.Process) -> str:
        if process.stderr is None:
            return ""
        try:
            data = await asyncio.wait_for(process.stderr.read(4096), timeout=0.1)
        except TimeoutError:
            return ""
        return data.decode("utf-8", errors="replace")[-1000:]
