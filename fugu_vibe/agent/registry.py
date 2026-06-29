"""Local tool registry for Fugu Responses function calls."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fugu_vibe.tools import FileTools, FileToolError


@dataclass
class ToolRegistry:
    """Register and dispatch local tools."""

    file_tools: FileTools

    def schemas(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "name": "file.list",
                "description": "List files in the current workspace. Read-only.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "pattern": {"type": "string", "default": "**/*"},
                        "limit": {"type": "integer", "default": 200},
                    },
                },
            },
            {
                "type": "function",
                "name": "file.read",
                "description": "Read a UTF-8 text file from the workspace. Read-only.",
                "parameters": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            },
            {
                "type": "function",
                "name": "file.search",
                "description": "Search UTF-8 workspace files for a literal query. Read-only.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "pattern": {"type": "string", "default": "**/*"},
                        "limit": {"type": "integer", "default": 50},
                    },
                    "required": ["query"],
                },
            },
        ]

    async def dispatch(self, name: str, arguments: str | dict[str, Any]) -> dict[str, Any]:
        args = self._parse_arguments(arguments)
        try:
            if name == "file.list":
                files = self.file_tools.list_files(
                    pattern=str(args.get("pattern", "**/*")),
                    limit=int(args.get("limit", 200)),
                )
                return {"ok": True, "files": files, "count": len(files)}
            if name == "file.read":
                content = self.file_tools.read_file(Path(str(args["path"])))
                return {"ok": True, "path": str(args["path"]), "content": content}
            if name == "file.search":
                matches = self.file_tools.search(
                    query=str(args["query"]),
                    pattern=str(args.get("pattern", "**/*")),
                    limit=int(args.get("limit", 50)),
                )
                return {"ok": True, "matches": matches, "count": len(matches)}
        except (KeyError, ValueError, FileToolError) as e:
            return {"ok": False, "error": str(e)}

        return {"ok": False, "error": f"Unknown tool: {name}"}

    def _parse_arguments(self, arguments: str | dict[str, Any]) -> dict[str, Any]:
        if isinstance(arguments, dict):
            return arguments
        if not arguments:
            return {}
        try:
            data = json.loads(arguments)
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}
