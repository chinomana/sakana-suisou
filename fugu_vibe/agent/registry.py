"""Local tool registry for Fugu Responses function calls."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fugu_vibe.tools import (
    FileToolError,
    FileTools,
    GitToolError,
    GitTools,
    TerminalTool,
    TerminalToolError,
)


@dataclass
class ToolRegistry:
    """Register and dispatch local tools."""

    file_tools: FileTools
    terminal_tool: TerminalTool | None = None
    git_tools: GitTools | None = None

    def schemas(self) -> list[dict[str, Any]]:
        schemas = [
            self._schema(
                "file_list",
                "List workspace files with size and modified-time metadata. Read-only.",
                {
                    "pattern": {"type": "string", "default": "**/*"},
                    "limit": {"type": "integer", "default": 200},
                },
            ),
            self._schema(
                "file_glob",
                "Find workspace files by glob pattern with structured metadata. Read-only.",
                {
                    "pattern": {"type": "string", "default": "**/*"},
                    "limit": {"type": "integer", "default": 200},
                },
            ),
            self._schema(
                "file_read",
                "Read a UTF-8 text file with line metadata. Read-only.",
                {
                    "path": {"type": "string"},
                    "start_line": {"type": "integer", "default": 1},
                    "limit": {"type": "integer", "default": 200},
                },
                required=["path"],
            ),
            self._schema(
                "file_search",
                "Search UTF-8 workspace files for a literal query or regular expression. Read-only.",
                {
                    "query": {"type": "string"},
                    "pattern": {"type": "string", "default": "**/*"},
                    "limit": {"type": "integer", "default": 50},
                    "regex": {"type": "boolean", "default": False},
                },
                required=["query"],
            ),
            self._schema(
                "file_grep",
                "Search workspace files with a regular expression. Read-only alias for file_search(regex=true).",
                {
                    "pattern_regex": {"type": "string"},
                    "file_glob": {"type": "string", "default": "**/*"},
                    "limit": {"type": "integer", "default": 50},
                },
                required=["pattern_regex"],
            ),
            self._schema(
                "file_write",
                "Create or overwrite a UTF-8 text file in the current workspace.",
                {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                    "overwrite": {"type": "boolean", "default": True},
                },
                required=["path", "content"],
            ),
            self._schema(
                "file_edit",
                "Replace an exact string in a UTF-8 text file without rewriting the whole file.",
                {
                    "path": {"type": "string"},
                    "old_string": {"type": "string"},
                    "new_string": {"type": "string"},
                    "replace_all": {"type": "boolean", "default": False},
                },
                required=["path", "old_string", "new_string"],
            ),
            self._schema(
                "file_delete",
                "Delete a file from the current workspace.",
                {"path": {"type": "string"}},
                required=["path"],
            ),
            self._schema(
                "file_mkdir",
                "Create a directory in the current workspace.",
                {"path": {"type": "string"}},
                required=["path"],
            ),
        ]
        if self.terminal_tool is not None:
            schemas.extend(
                [
                    self._schema(
                        "bash",
                        "Run a shell command in the workspace and return structured stdout/stderr/exit-code data.",
                        {
                            "command": {"type": "string"},
                            "cwd": {"type": "string", "default": "."},
                        },
                        required=["command"],
                    ),
                    self._schema(
                        "run_test",
                        "Run the project's test command and return a structured test summary.",
                        {
                            "command": {"type": "string", "default": "pytest"},
                            "cwd": {"type": "string", "default": "."},
                        },
                    ),
                    self._schema(
                        "run_lint",
                        "Run the project's lint/type-check command and return structured results.",
                        {
                            "command": {"type": "string", "default": "ruff check ."},
                            "cwd": {"type": "string", "default": "."},
                        },
                    ),
                ]
            )
        if self.git_tools is not None:
            schemas.extend(
                [
                    self._schema("git_status", "Return structured git status. Read-only.", {}),
                    self._schema(
                        "git_diff",
                        "Return git diff text and metadata. Read-only.",
                        {
                            "path": {"type": "string", "default": ""},
                            "cached": {"type": "boolean", "default": False},
                        },
                    ),
                    self._schema(
                        "git_log",
                        "Return recent commits. Read-only.",
                        {"limit": {"type": "integer", "default": 10}},
                    ),
                    self._schema(
                        "git_show",
                        "Show a commit or revision with stat and patch. Read-only.",
                        {"revision": {"type": "string", "default": "HEAD"}},
                    ),
                ]
            )
        return schemas

    async def dispatch(self, name: str, arguments: str | dict[str, Any]) -> dict[str, Any]:
        name = name.replace(".", "_")
        args = self._parse_arguments(arguments)
        try:
            if name in {"file_list", "file_glob"}:
                return {
                    "ok": True,
                    **self.file_tools.glob_files(
                        pattern=str(args.get("pattern", "**/*")),
                        limit=int(args.get("limit", 200)),
                    ),
                }
            if name == "file_read":
                return {
                    "ok": True,
                    **self.file_tools.read_file_structured(
                        Path(str(args["path"])),
                        start_line=int(args.get("start_line", 1)),
                        limit=int(args.get("limit", 200)),
                    ),
                }
            if name == "file_search":
                return {
                    "ok": True,
                    **self.file_tools.search_structured(
                        query=str(args["query"]),
                        pattern=str(args.get("pattern", "**/*")),
                        limit=int(args.get("limit", 50)),
                        regex=self._bool_arg(args.get("regex", False)),
                    ),
                }
            if name == "file_grep":
                return {
                    "ok": True,
                    **self.file_tools.search_structured(
                        query=str(args["pattern_regex"]),
                        pattern=str(args.get("file_glob", "**/*")),
                        limit=int(args.get("limit", 50)),
                        regex=True,
                    ),
                }
            if name == "file_write":
                return {
                    "ok": True,
                    **self.file_tools.write_file_structured(
                        Path(str(args["path"])),
                        content=str(args["content"]),
                        overwrite=self._bool_arg(args.get("overwrite", True)),
                    ),
                }
            if name == "file_edit":
                return {
                    "ok": True,
                    **self.file_tools.edit_file(
                        Path(str(args["path"])),
                        old_string=str(args["old_string"]),
                        new_string=str(args["new_string"]),
                        replace_all=self._bool_arg(args.get("replace_all", False)),
                    ),
                }
            if name == "file_delete":
                return {"ok": True, **self.file_tools.delete_file(Path(str(args["path"])))}
            if name == "file_mkdir":
                path = self.file_tools.make_directory(Path(str(args["path"])))
                return {"ok": True, "path": path}
            if name == "bash":
                result = await self._run_terminal(str(args["command"]), str(args.get("cwd", ".")))
                return {"ok": result["exit_code"] == 0 and not result["timed_out"], **result}
            if name == "run_test":
                result = await self._run_terminal(str(args.get("command", "pytest")), str(args.get("cwd", ".")))
                return {
                    "ok": result["exit_code"] == 0 and not result["timed_out"],
                    **result,
                    "summary": self._summarize_tests(result),
                }
            if name == "run_lint":
                result = await self._run_terminal(str(args.get("command", "ruff check .")), str(args.get("cwd", ".")))
                return {"ok": result["exit_code"] == 0 and not result["timed_out"], **result}
            if name == "git_status":
                return {"ok": True, **self._git().status()}
            if name == "git_diff":
                path = str(args.get("path", "")) or None
                return {"ok": True, **self._git().diff(path=path, cached=self._bool_arg(args.get("cached", False)))}
            if name == "git_log":
                return {"ok": True, **self._git().log(limit=int(args.get("limit", 10)))}
            if name == "git_show":
                return {"ok": True, **self._git().show(revision=str(args.get("revision", "HEAD")))}
        except (KeyError, ValueError, FileToolError, TerminalToolError, GitToolError) as e:
            return {"ok": False, "error": str(e), "tool": name}

        return {"ok": False, "error": f"Unknown tool: {name}", "tool": name}

    def _schema(
        self,
        name: str,
        description: str,
        properties: dict[str, Any],
        required: list[str] | None = None,
    ) -> dict[str, Any]:
        schema = {
            "type": "function",
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "additionalProperties": False,
            },
            "strict": True,
        }
        if required:
            schema["parameters"]["required"] = required
        return schema

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

    def _bool_arg(self, value: Any) -> bool:
        if isinstance(value, str):
            return value.lower() in {"1", "true", "yes", "on"}
        return bool(value)

    async def _run_terminal(self, command: str, cwd: str = ".") -> dict[str, Any]:
        if self.terminal_tool is None:
            raise TerminalToolError("Terminal tool is not configured")
        return await self.terminal_tool.run_structured(command, cwd=cwd)

    def _git(self) -> GitTools:
        if self.git_tools is None:
            raise GitToolError("Git tools are not configured")
        return self.git_tools

    def _summarize_tests(self, result: dict[str, Any]) -> dict[str, Any]:
        output = f"{result.get('stdout', '')}\n{result.get('stderr', '')}"
        summary: dict[str, Any] = {"passed": None, "failed": None, "errors": None, "skipped": None}
        patterns = {
            "passed": r"(\d+) passed",
            "failed": r"(\d+) failed",
            "errors": r"(\d+) errors?",
            "skipped": r"(\d+) skipped",
        }
        for key, pattern in patterns.items():
            match = re.search(pattern, output)
            if match:
                summary[key] = int(match.group(1))
        known_counts = [value for value in summary.values() if isinstance(value, int)]
        summary["total"] = sum(known_counts) if known_counts else None
        summary["status"] = "passed" if result.get("exit_code") == 0 else "failed"
        return summary
