"""Workspace MCP server configuration store."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fugu_vibe.mcp.client import MCPServer

DEFAULT_MCP_CONFIG = Path(".fugu-vibe") / "mcp.json"


class MCPConfigStore:
    """Read and write MCP server definitions for one workspace."""

    def __init__(self, workspace: Path | str | None = None, path: Path | str | None = None):
        root = Path(workspace or Path.cwd())
        self.path = Path(path) if path else root / DEFAULT_MCP_CONFIG

    def list_servers(self) -> list[MCPServer]:
        payload = self._read()
        servers = payload.get("servers", {})
        if not isinstance(servers, dict):
            return []
        result: list[MCPServer] = []
        for name, config in servers.items():
            if not isinstance(config, dict):
                continue
            command = config.get("command")
            if not command:
                continue
            args = config.get("args", [])
            env = config.get("env", {})
            result.append(
                MCPServer(
                    name=str(name),
                    command=str(command),
                    args=[str(arg) for arg in args] if isinstance(args, list) else [],
                    env={str(k): str(v) for k, v in env.items()} if isinstance(env, dict) else {},
                )
            )
        return result

    def get(self, name: str) -> MCPServer | None:
        return next((server for server in self.list_servers() if server.name == name), None)

    def add(self, server: MCPServer) -> None:
        payload = self._read()
        servers = payload.setdefault("servers", {})
        if not isinstance(servers, dict):
            servers = {}
            payload["servers"] = servers
        servers[server.name] = {
            "command": server.command,
            "args": server.args,
            "env": server.env,
        }
        self._write(payload)

    def remove(self, name: str) -> bool:
        payload = self._read()
        servers = payload.get("servers", {})
        if not isinstance(servers, dict) or name not in servers:
            return False
        del servers[name]
        self._write(payload)
        return True

    def _read(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"servers": {}}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {"servers": {}}
        return payload if isinstance(payload, dict) else {"servers": {}}

    def _write(self, payload: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
