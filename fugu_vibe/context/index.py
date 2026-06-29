"""Lightweight codebase indexing for Fugu context assembly."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fugu_vibe.tools.files import DEFAULT_EXCLUDES

MAX_INDEX_FILE_BYTES = 256 * 1024
DEFAULT_MAX_FILES = 1_000
PREVIEW_LINES = 30
SYMBOL_LIMIT = 40

LANGUAGE_BY_SUFFIX = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".c": "c",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".h": "c-header",
    ".hpp": "cpp-header",
    ".md": "markdown",
    ".toml": "toml",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
}

SYMBOL_PATTERNS = {
    "python": re.compile(r"^\s*(?:async\s+def|def|class)\s+([A-Za-z_][\w]*)", re.MULTILINE),
    "javascript": re.compile(
        r"^\s*(?:export\s+)?(?:async\s+)?(?:function|class)\s+([A-Za-z_$][\w$]*)",
        re.MULTILINE,
    ),
    "typescript": re.compile(
        r"^\s*(?:export\s+)?(?:async\s+)?(?:function|class|interface|type)\s+([A-Za-z_$][\w$]*)",
        re.MULTILINE,
    ),
    "go": re.compile(r"^\s*func\s+(?:\([^)]*\)\s*)?([A-Za-z_][\w]*)", re.MULTILINE),
    "rust": re.compile(r"^\s*(?:pub\s+)?(?:async\s+)?(?:fn|struct|enum|trait)\s+([A-Za-z_][\w]*)", re.MULTILINE),
    "java": re.compile(
        r"^\s*(?:public|private|protected)?\s*(?:static\s+)?(?:class|interface|enum)\s+([A-Za-z_][\w]*)",
        re.MULTILINE,
    ),
}


@dataclass
class CodebaseIndex:
    """Build and cache a small file tree plus symbol summary."""

    workspace: Path
    cache_path: Path | None = None
    max_files: int = DEFAULT_MAX_FILES
    max_file_bytes: int = MAX_INDEX_FILE_BYTES
    files: list[dict[str, Any]] = field(default_factory=list)
    truncated: bool = False

    def __post_init__(self) -> None:
        self.workspace = self.workspace.expanduser().resolve()
        if self.cache_path is None:
            self.cache_path = self.workspace / ".fugu-vibe" / "index.json"

    def build(self) -> dict[str, Any]:
        """Scan the workspace and persist a structured index."""
        files: list[dict[str, Any]] = []
        self.truncated = False
        for path in sorted(self.workspace.rglob("*")):
            if len(files) >= self.max_files:
                self.truncated = True
                break
            if not path.is_file() or self._is_excluded(path):
                continue
            entry = self._entry_for(path)
            if entry is not None:
                files.append(entry)
        self.files = files
        data = self.to_dict()
        self.save(data)
        return data

    def load(self) -> dict[str, Any] | None:
        """Load the cached index if it exists."""
        if self.cache_path is None or not self.cache_path.exists():
            return None
        data = json.loads(self.cache_path.read_text(encoding="utf-8"))
        self.files = list(data.get("files", []))
        self.truncated = bool(data.get("truncated", False))
        return data

    def load_or_build(self) -> dict[str, Any]:
        """Load cached index or build a new one."""
        cached = self.load()
        return cached if cached is not None else self.build()

    def save(self, data: dict[str, Any] | None = None) -> None:
        """Persist the index atomically."""
        if self.cache_path is None:
            return
        payload = data or self.to_dict()
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.cache_path.with_suffix(".json.tmp")
        tmp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp_path.replace(self.cache_path)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable index snapshot."""
        return {
            "workspace": str(self.workspace),
            "files": self.files,
            "count": len(self.files),
            "truncated": self.truncated,
        }

    def select_for_context(self, query: str, max_files: int = 10) -> list[dict[str, Any]]:
        """Select relevant files using simple lexical scoring."""
        terms = self._query_terms(query)
        if not terms:
            return self.files[:max_files]
        scored: list[tuple[int, dict[str, Any]]] = []
        for entry in self.files:
            haystack = " ".join(
                [
                    str(entry.get("path", "")),
                    str(entry.get("language", "")),
                    " ".join(str(symbol) for symbol in entry.get("symbols", [])),
                    str(entry.get("preview", "")),
                ]
            ).lower()
            score = sum(3 if term in str(entry.get("path", "")).lower() else 0 for term in terms)
            score += sum(1 for term in terms if term in haystack)
            if score:
                scored.append((score, entry))
        return [entry for _, entry in sorted(scored, key=lambda item: (-item[0], item[1]["path"]))[:max_files]]

    def overview(self, max_files: int = 80) -> str:
        """Render a compact text overview suitable for model context."""
        lines = [f"Workspace index: {len(self.files)} file(s){' (truncated)' if self.truncated else ''}."]
        for entry in self.files[:max_files]:
            symbols = entry.get("symbols", [])
            symbol_text = f" symbols: {', '.join(symbols[:8])}" if symbols else ""
            lines.append(f"- {entry['path']} ({entry.get('language', 'text')}, {entry['size_bytes']} bytes){symbol_text}")
        if len(self.files) > max_files:
            lines.append(f"... {len(self.files) - max_files} more file(s) omitted from overview")
        return "\n".join(lines)

    def _entry_for(self, path: Path) -> dict[str, Any] | None:
        stat = path.stat()
        language = LANGUAGE_BY_SUFFIX.get(path.suffix.lower(), "text")
        entry: dict[str, Any] = {
            "path": str(path.relative_to(self.workspace)),
            "size_bytes": stat.st_size,
            "modified_at": stat.st_mtime,
            "language": language,
            "symbols": [],
            "preview": "",
        }
        if stat.st_size > self.max_file_bytes:
            entry["truncated"] = True
            return entry
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return None
        entry["symbols"] = self._extract_symbols(language, content)
        entry["preview"] = self._preview(content)
        entry["truncated"] = False
        return entry

    def _extract_symbols(self, language: str, content: str) -> list[str]:
        pattern = SYMBOL_PATTERNS.get(language)
        if pattern is None:
            return []
        symbols = pattern.findall(content)
        return list(dict.fromkeys(symbols))[:SYMBOL_LIMIT]

    def _preview(self, content: str) -> str:
        lines = [line.strip() for line in content.splitlines() if line.strip()]
        return "\n".join(lines[:PREVIEW_LINES])

    def _query_terms(self, query: str) -> list[str]:
        return [term.lower() for term in re.findall(r"[A-Za-z0-9_\-.]+", query) if len(term) > 1]

    def _is_excluded(self, path: Path) -> bool:
        try:
            relative = path.resolve().relative_to(self.workspace)
        except ValueError:
            return True
        if set(relative.parts) & DEFAULT_EXCLUDES:
            return True
        return any(part.endswith(".egg-info") for part in relative.parts)
