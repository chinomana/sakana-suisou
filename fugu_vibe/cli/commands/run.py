"""`fugu-vibe run` - non-interactive headless execution."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import click
from rich.console import Console

from fugu_vibe.core.headless import run_headless

console = Console()


@click.command(name="run")
@click.argument("prompt", required=False)
@click.option("--script", "script_path", type=click.Path(exists=True, dir_okay=False, path_type=Path), help="Read prompt from a markdown/text file")
@click.option("--json", "json_output", is_flag=True, help="Print structured JSON result")
@click.pass_context
def run_command(ctx: click.Context, prompt: str | None, script_path: Path | None, json_output: bool) -> None:
    """Run one prompt without starting the interactive session."""
    if script_path:
        prompt = script_path.read_text(encoding="utf-8")
    if not prompt:
        raise click.ClickException("Provide a PROMPT or --script PATH")
    result = asyncio.run(run_headless(prompt, ctx.obj["config"], workspace=ctx.obj.get("workspace", Path.cwd())))
    if json_output:
        console.print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    else:
        console.print(result.content)
    raise SystemExit(0 if result.ok else 1)
