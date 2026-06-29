"""Workspace-safe read-only file tools."""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from pathlib import Path


DEFAULT_EXCLUDES = {
    ".git",
    ".fugu-vibe",
    ".fugu-worktrees",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    ".venv312",
    "__pycache__",
    "dist",
    "build",
    "node_modules",
}

MAX_READ_BYTES = 512 * 1024
MAX_SEARCH_BYTES = 256 * 1024


class FileToolError(Exception):
    """Raised when a file tool request is invalid or unsafe."""


@dataclass
class FileTools:
    """Read-only file operations constrained to one workspace."""

    workspace: Path

    def __post_init__(self) -> None:
        self.workspace = self.workspace.expanduser().resolve()

    def list_files(self, pattern: str = "**/*", limit: int = 200) -> list[str]:
        """List workspace files matching a glob pattern."""
        results: list[str] = []
        for path in sorted(self.workspace.glob(pattern)):
            if len(results) >= limit:
                break
            if not path.is_file() or self._is_excluded(path):
                continue
            results.append(self._relative(path))
        return results

    def read_file(self, path: str | Path, max_bytes: int = MAX_READ_BYTES) -> str:
        """Read a UTF-8 text file from the workspace."""
        resolved = self._resolve(path)
        if not resolved.is_file():
            raise FileToolError(f"Not a file: {path}")
        if self._is_excluded(resolved):
            raise FileToolError(f"Path is excluded: {path}")
        size = resolved.stat().st_size
        if size > max_bytes:
            raise FileToolError(f"File is too large to read ({size} bytes): {path}")
        try:
            return resolved.read_text(encoding="utf-8")
        except UnicodeDecodeError as e:
            raise FileToolError(f"File is not UTF-8 text: {path}") from e

    def search(
        self,
        query: str,
        pattern: str = "**/*",
        limit: int = 50,
        max_file_bytes: int = MAX_SEARCH_BYTES,
    ) -> list[dict[str, str | int]]:
        """Search UTF-8 workspace files for a literal query."""
        if not query:
            raise FileToolError("Search query must not be empty")

        matches: list[dict[str, str | int]] = []
        for path in sorted(self.workspace.glob(pattern)):
            if len(matches) >= limit:
                break
            if not path.is_file() or self._is_excluded(path):
                continue
            if path.stat().st_size > max_file_bytes:
                continue
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except UnicodeDecodeError:
                continue
            for line_number, line in enumerate(lines, start=1):
                if query in line:
                    matches.append(
                        {
                            "path": self._relative(path),
                            "line": line_number,
                            "text": line.strip(),
                        }
                    )
                    if len(matches) >= limit:
                        break
        return matches

    def _resolve(self, path: str | Path) -> Path:
        candidate = Path(path).expanduser()
        if not candidate.is_absolute():
            candidate = self.workspace / candidate
        resolved = candidate.resolve()
        if not resolved.is_relative_to(self.workspace):
            raise FileToolError(f"Path escapes workspace: {path}")
        return resolved

    def _relative(self, path: Path) -> str:
        return str(path.resolve().relative_to(self.workspace))

    def _is_excluded(self, path: Path) -> bool:
        try:
            relative = path.resolve().relative_to(self.workspace)
        except ValueError:
            return True
        parts = set(relative.parts)
        if parts & DEFAULT_EXCLUDES:
            return True
        return any(fnmatch.fnmatch(part, "*.egg-info") for part in relative.parts)
