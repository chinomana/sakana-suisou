"""Workspace-safe terminal command execution."""

from __future__ import annotations

import asyncio
import json
import shlex
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4


DANGEROUS_PATTERNS = (
    "rm -rf",
    "git reset --hard",
    "git checkout --",
    "sudo ",
    "chmod -R",
    "chown ",
    "curl ",
    "wget ",
    "| sh",
    "| bash",
    "bash <",
    "sh <",
    "> /dev/",
)

SAFE_PREFIXES = (
    "git status",
    "git diff",
    "git log",
    "pytest",
    "python -m pytest",
    "ruff check",
    "mypy",
    "npm test",
    "pnpm test",
)


class TerminalToolError(Exception):
    """Raised when terminal execution is disabled or unsafe."""


@dataclass
class TerminalResult:
    """Result of a terminal command."""

    run_id: str
    command: str
    cwd: Path
    exit_code: int | None
    stdout: str
    stderr: str
    duration_seconds: float
    timed_out: bool
    log_path: Path


@dataclass
class TerminalTool:
    """Run shell commands constrained to a workspace."""

    workspace: Path
    enabled: bool = False
    approval: str = "off"
    timeout_seconds: int = 120
    max_output_chars: int = 20_000

    def __post_init__(self) -> None:
        self.workspace = self.workspace.expanduser().resolve()
        self.log_dir = self.workspace / ".fugu-vibe" / "tool-runs"
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def status(self) -> dict[str, Any]:
        return {
            "terminal_enabled": self.enabled,
            "terminal_approval": self.approval,
            "timeout_seconds": self.timeout_seconds,
            "max_output_chars": self.max_output_chars,
        }

    async def run(self, command: str, cwd: str | Path | None = None) -> TerminalResult:
        """Run a shell command after policy checks."""
        if not self.enabled or self.approval == "off":
            raise TerminalToolError("Terminal tools are disabled. Enable tools.terminal_enabled first.")
        self._check_command(command)
        resolved_cwd = self._resolve_cwd(cwd)

        started = datetime.now()
        process = await asyncio.create_subprocess_shell(
            command,
            cwd=str(resolved_cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        timed_out = False
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(), timeout=self.timeout_seconds
            )
        except asyncio.TimeoutError:
            timed_out = True
            process.kill()
            stdout_bytes, stderr_bytes = await process.communicate()

        finished = datetime.now()
        stdout = stdout_bytes.decode("utf-8", errors="replace")
        stderr = stderr_bytes.decode("utf-8", errors="replace")
        run_id = uuid4().hex[:12]
        log_path = self._write_log(
            run_id=run_id,
            command=command,
            cwd=resolved_cwd,
            exit_code=process.returncode,
            stdout=stdout,
            stderr=stderr,
            duration_seconds=(finished - started).total_seconds(),
            timed_out=timed_out,
        )
        return TerminalResult(
            run_id=run_id,
            command=command,
            cwd=resolved_cwd,
            exit_code=process.returncode,
            stdout=self._truncate(stdout),
            stderr=self._truncate(stderr),
            duration_seconds=(finished - started).total_seconds(),
            timed_out=timed_out,
            log_path=log_path,
        )

    def _check_command(self, command: str) -> None:
        normalized = " ".join(command.strip().split())
        if not normalized:
            raise TerminalToolError("Command must not be empty")
        lowered = normalized.lower()
        for pattern in DANGEROUS_PATTERNS:
            if pattern in lowered:
                raise TerminalToolError(f"Command blocked by safety policy: {pattern}")
        if self.approval == "auto-safe" and not lowered.startswith(SAFE_PREFIXES):
            raise TerminalToolError("Command is not in the auto-safe allowlist")

    def _resolve_cwd(self, cwd: str | Path | None) -> Path:
        if cwd is None:
            return self.workspace
        path = Path(cwd).expanduser()
        if not path.is_absolute():
            path = self.workspace / path
        resolved = path.resolve()
        if not resolved.is_dir():
            raise TerminalToolError(f"cwd is not a directory: {cwd}")
        if not resolved.is_relative_to(self.workspace):
            raise TerminalToolError(f"cwd escapes workspace: {cwd}")
        return resolved

    def _truncate(self, text: str) -> str:
        if len(text) <= self.max_output_chars:
            return text
        omitted = len(text) - self.max_output_chars
        return text[: self.max_output_chars] + f"\n...[truncated {omitted} chars]"

    def _write_log(
        self,
        run_id: str,
        command: str,
        cwd: Path,
        exit_code: int | None,
        stdout: str,
        stderr: str,
        duration_seconds: float,
        timed_out: bool,
    ) -> Path:
        log_path = self.log_dir / f"{run_id}.json"
        data = {
            "run_id": run_id,
            "command": command,
            "argv_preview": shlex.split(command) if command else [],
            "cwd": str(cwd),
            "exit_code": exit_code,
            "duration_seconds": duration_seconds,
            "timed_out": timed_out,
            "stdout": stdout,
            "stderr": stderr,
            "created_at": datetime.now().isoformat(),
        }
        tmp_path = log_path.with_suffix(".json.tmp")
        tmp_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp_path.replace(log_path)
        return log_path
