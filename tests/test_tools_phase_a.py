"""Tests for Phase A structured local tools."""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

import pytest

from fugu_vibe.agent.registry import ToolRegistry
from fugu_vibe.tools import FileToolError, FileTools, GitTools, TerminalTool


@pytest.mark.asyncio
async def test_registry_exposes_structured_phase_a_tools(tmp_path: Path) -> None:
    registry = ToolRegistry(
        FileTools(tmp_path),
        terminal_tool=TerminalTool(tmp_path, enabled=True, approval="auto-safe"),
        git_tools=GitTools(tmp_path),
    )

    names = {schema["name"] for schema in registry.schemas()}

    assert {
        "file_edit",
        "file_delete",
        "file_glob",
        "file_grep",
        "bash",
        "run_test",
        "run_lint",
        "git_status",
        "git_diff",
    } <= names


@pytest.mark.asyncio
async def test_file_read_search_edit_and_delete_are_structured(tmp_path: Path) -> None:
    tools = FileTools(tmp_path)
    registry = ToolRegistry(tools)
    target = tmp_path / "app.py"
    target.write_text("def hello():\n    return 'hi'\n", encoding="utf-8")

    read = await registry.dispatch("file_read", {"path": "app.py", "start_line": 1, "limit": 1})
    assert read["ok"] is True
    assert read["lines"] == [{"line": 1, "text": "def hello():"}]
    assert read["truncated"] is True

    grep = await registry.dispatch("file_grep", {"pattern_regex": r"return '.+'", "file_glob": "*.py"})
    assert grep["ok"] is True
    assert grep["matches"][0]["path"] == "app.py"
    assert grep["matches"][0]["column"] == 5

    edit = await registry.dispatch(
        "file_edit",
        {"path": "app.py", "old_string": "return 'hi'", "new_string": "return 'hello'"},
    )
    assert edit["ok"] is True
    assert edit["replacements"] == 1
    assert "return 'hello'" in target.read_text(encoding="utf-8")

    delete = await registry.dispatch("file_delete", {"path": "app.py"})
    assert delete["ok"] is True
    assert delete["deleted"] is True
    assert not target.exists()


def test_file_edit_requires_unique_match(tmp_path: Path) -> None:
    target = tmp_path / "data.txt"
    target.write_text("same\nsame\n", encoding="utf-8")

    with pytest.raises(FileToolError, match="matched 2 times"):
        FileTools(tmp_path).edit_file("data.txt", "same", "different")


@pytest.mark.asyncio
async def test_bash_and_run_test_return_structured_results(tmp_path: Path) -> None:
    registry = ToolRegistry(
        FileTools(tmp_path),
        terminal_tool=TerminalTool(tmp_path, enabled=True, approval="auto-safe", timeout_seconds=10),
    )

    bash = await registry.dispatch("bash", {"command": "python -m pytest --version"})
    assert bash["ok"] is True
    assert bash["exit_code"] == 0
    assert bash["command"] == "python -m pytest --version"
    assert "pytest" in bash["stdout"].lower()

    test_file = tmp_path / "test_sample.py"
    test_file.write_text("def test_pass():\n    assert True\n", encoding="utf-8")
    run = await registry.dispatch("run_test", {"command": "python -m pytest -q"})
    assert run["ok"] is True
    assert run["summary"]["passed"] == 1
    assert run["summary"]["status"] == "passed"


@pytest.mark.asyncio
async def test_git_tools_return_structured_status_and_diff(tmp_path: Path) -> None:
    await asyncio.to_thread(_initialize_git_repo, tmp_path)
    target = tmp_path / "tracked.txt"
    target.write_text("after\n", encoding="utf-8")

    registry = ToolRegistry(FileTools(tmp_path), git_tools=GitTools(tmp_path))

    status = await registry.dispatch("git_status", {})
    assert status["ok"] is True
    assert status["dirty"] is True
    assert status["entries"] == [{"status": " M", "path": "tracked.txt"}]

    diff = await registry.dispatch("git_diff", {"path": "tracked.txt"})
    assert diff["ok"] is True
    assert diff["changed"] is True
    assert "-before" in diff["diff"]
    assert "+after" in diff["diff"]



def _initialize_git_repo(path: Path) -> None:
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=path, check=True)
    target = path / "tracked.txt"
    target.write_text("before\n", encoding="utf-8")
    subprocess.run(["git", "add", "tracked.txt"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=path, check=True, capture_output=True)

