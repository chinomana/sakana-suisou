"""Structured, workspace-safe git tools."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class GitToolError(Exception):
    """Raised when a git tool request fails or is unsafe."""


@dataclass
class GitTools:
    """Read-only git operations constrained to one workspace."""

    workspace: Path
    timeout_seconds: int = 30
    max_output_chars: int = 20_000

    def __post_init__(self) -> None:
        self.workspace = self.workspace.expanduser().resolve()

    def status(self) -> dict[str, Any]:
        """Return structured git status."""
        result = self._run_git(["status", "--short", "--branch"])
        branch = ""
        entries: list[dict[str, str]] = []
        for line in result["stdout"].splitlines():
            if line.startswith("## "):
                branch = line[3:]
                continue
            if not line:
                continue
            entries.append(
                {
                    "status": line[:2],
                    "path": line[3:] if len(line) > 3 else "",
                }
            )
        return {
            **result,
            "branch": branch,
            "entries": entries,
            "dirty": bool(entries),
            "count": len(entries),
        }

    def diff(self, path: str | None = None, cached: bool = False) -> dict[str, Any]:
        """Return git diff text and metadata."""
        args = ["diff"]
        if cached:
            args.append("--cached")
        if path:
            self._validate_relative_path(path)
            args.extend(["--", path])
        result = self._run_git(args)
        diff = result["stdout"]
        return {
            **result,
            "diff": diff,
            "path": path,
            "cached": cached,
            "changed": bool(diff.strip()),
            "truncated": result["stdout_truncated"],
        }

    def log(self, limit: int = 10) -> dict[str, Any]:
        """Return recent git commits."""
        limit = min(max(limit, 1), 100)
        result = self._run_git(
            [
                "log",
                f"--max-count={limit}",
                "--pretty=format:%H%x09%an%x09%ad%x09%s",
                "--date=iso",
            ]
        )
        commits: list[dict[str, str]] = []
        for line in result["stdout"].splitlines():
            parts = line.split("\t", 3)
            if len(parts) != 4:
                continue
            commits.append(
                {"hash": parts[0], "author": parts[1], "date": parts[2], "subject": parts[3]}
            )
        return {**result, "commits": commits, "count": len(commits)}

    def show(self, revision: str = "HEAD", max_chars: int | None = None) -> dict[str, Any]:
        """Return a commit or object via git show."""
        if not revision or revision.startswith("-"):
            raise GitToolError("revision must not be empty or start with '-'")
        result = self._run_git(["show", "--stat", "--patch", revision], max_chars=max_chars)
        return {**result, "revision": revision, "content": result["stdout"]}

    def _run_git(self, args: list[str], max_chars: int | None = None) -> dict[str, Any]:
        try:
            completed = subprocess.run(
                ["git", *args],
                cwd=self.workspace,
                check=False,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
            )
        except FileNotFoundError as e:
            raise GitToolError("git executable was not found") from e
        except subprocess.TimeoutExpired as e:
            raise GitToolError(f"git command timed out after {self.timeout_seconds}s") from e

        stdout, stdout_truncated = self._truncate(completed.stdout, max_chars)
        stderr, stderr_truncated = self._truncate(completed.stderr, max_chars)
        return {
            "command": "git " + " ".join(args),
            "exit_code": completed.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "stdout_truncated": stdout_truncated,
            "stderr_truncated": stderr_truncated,
        }

    def _truncate(self, text: str, max_chars: int | None = None) -> tuple[str, bool]:
        limit = max_chars or self.max_output_chars
        if len(text) <= limit:
            return text, False
        omitted = len(text) - limit
        return text[:limit] + f"\n...[truncated {omitted} chars]", True

    def _validate_relative_path(self, path: str) -> None:
        candidate = (self.workspace / path).resolve()
        if not candidate.is_relative_to(self.workspace):
            raise GitToolError(f"Path escapes workspace: {path}")
