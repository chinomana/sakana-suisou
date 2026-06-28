"""
`fugu-vibe vibe` - Main interactive vibe coding session.

This is the primary command: opens an interactive session with
orchestration visualization, accepts text/voice input, and manages
tasks in real-time.
"""

from __future__ import annotations

import asyncio
import shlex
from pathlib import Path
from typing import TYPE_CHECKING

import click
from prompt_toolkit import PromptSession
from prompt_toolkit.key_binding import KeyBindings
from rich.console import Console
from rich.markdown import Markdown

from fugu_vibe.api.client import FuguClient
from fugu_vibe.core.attachments import build_content_parts
from fugu_vibe.core.event_bus import EventBus, EventType
from fugu_vibe.core.event_log import EventLogWriter
from fugu_vibe.core.orchestration import OrchestrationAnalyzer
from fugu_vibe.core.session_output import SessionOutputWriter
from fugu_vibe.core.task_manager import TaskManager
from fugu_vibe.ui.dashboard import OrchestrationDashboard

if TYPE_CHECKING:
    from fugu_vibe.config import Config

console = Console()


@click.command()
@click.option("--model", "-m", help="Model to use")
@click.option("--effort", "-e", type=click.Choice(["high", "xhigh", "max"]), help="Reasoning effort")
@click.option("--web-search", "-w", is_flag=True, help="Enable web search")
@click.option(
    "--viz/--no-viz",
    default=False,
    help="Enable or disable orchestration visualization. Disabled by default for stable input.",
)
@click.option("--voice", "-v", is_flag=True, help="Enable voice input")
@click.option(
    "--file",
    "-f",
    "files",
    multiple=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Attach a PDF, image, or file to each prompt. Can be used multiple times.",
)
@click.option("--unlimited", "-u", is_flag=True, help="Unlimited prompt mode (no guardrails)")
@click.pass_context
def vibe_command(
    ctx: click.Context,
    model: str | None,
    effort: str | None,
    web_search: bool,
    viz: bool,
    voice: bool,
    files: tuple[Path, ...],
    unlimited: bool,
) -> None:
    """
    🚀 Start interactive vibe coding session.
    
    This is the main command - opens a full-screen dashboard with
    real-time orchestration visualization, and accepts text/voice input.
    
    Examples:
        fugu-vibe vibe                          # Default session
        fugu-vibe vibe --model fugu-ultra       # Use Fugu Ultra
        fugu-vibe vibe --effort xhigh           # Maximum reasoning
        fugu-vibe vibe --web-search             # Enable web search
        fugu-vibe vibe --viz                    # Enable dashboard visualization
        fugu-vibe vibe -f spec.pdf -f photo.png # Attach files
        fugu-vibe vibe --voice                  # Enable voice control
        fugu-vibe vibe --unlimited              # No prompt restrictions
    """
    config: Config = ctx.obj["config"]
    
    # Override with CLI options
    if model:
        config.model.default = model
    if effort:
        config.model.reasoning_effort = effort  # type: ignore
    if unlimited:
        config.prompt.unlimited_mode = True
    
    # Run async session
    asyncio.run(_vibe_session(config, web_search, viz, voice, list(files)))


async def _vibe_session(
    config: Config,
    web_search: bool,
    viz_enabled: bool,
    voice_enabled: bool,
    initial_files: list[Path],
) -> None:
    """Main vibe session loop."""
    
    # Initialize components
    event_bus = EventBus()
    event_log = EventLogWriter(event_bus)
    event_log.start()
    await event_bus.start()
    
    fugu_client = FuguClient(config)
    task_manager = TaskManager(config, fugu_client, event_bus)
    await task_manager.start()
    
    # Start dashboard
    dashboard = None
    if viz_enabled:
        dashboard = OrchestrationDashboard(config, event_bus)
        await dashboard.start()
    
    # Start voice if requested
    voice_pipeline = None
    if voice_enabled:
        from fugu_vibe.voice.pipeline import VoicePipeline
        voice_pipeline = VoicePipeline(config, task_manager, event_bus)
        try:
            await voice_pipeline.start()
            console.print("[green]🎤 Voice input enabled (press Space to talk)[/green]")
        except RuntimeError as e:
            console.print(f"[yellow]Voice unavailable: {e}[/yellow]")
    
    # Prompt session for keyboard input
    session = PromptSession(
        message="> ",
        multiline=False,
        enable_suspend=True,
    )
    output_writer = SessionOutputWriter()
    history: list[dict] = []
    
    console.print("\n[bold cyan]🐡 Fugu Vibe Session Started[/bold cyan]")
    console.print("Type your prompt and press Enter")
    attached_files = [path.expanduser().resolve() for path in initial_files]

    console.print("Commands: /attach /files /clear-files /status /tasks /quit /help")
    console.print("Exit: Ctrl+C or Ctrl+D\n")
    console.print(f"[dim]Session output: {output_writer.path}[/dim]")
    if attached_files:
        console.print(f"[dim]Attached {len(attached_files)} file(s). Use /files to list them.[/dim]\n")
    
    try:
        while True:
            try:
                # Get user input
                user_input = await session.prompt_async()
                user_input = user_input.strip()
                
                if not user_input:
                    continue
                
                # Handle commands
                if user_input.startswith("/"):
                    await _handle_command(
                        user_input, task_manager, event_bus, dashboard, attached_files
                    )
                    continue
                
                # Send to Fugu
                await _send_to_fugu(
                    user_input,
                    fugu_client,
                    event_bus,
                    config,
                    web_search,
                    attached_files,
                    history,
                    output_writer,
                )
                
            except KeyboardInterrupt:
                break
            except EOFError:
                break
                
    finally:
        # Cleanup
        if voice_pipeline:
            await voice_pipeline.stop()
        if dashboard:
            await dashboard.stop()
        await task_manager.close()
        await event_bus.close()
        await fugu_client.close()
        
        console.print("\n[dim]Session ended.[/dim]")


async def _send_to_fugu(
    prompt: str,
    client: FuguClient,
    event_bus: EventBus,
    config: Config,
    web_search: bool,
    files: list[Path],
    history: list[dict],
    output_writer: SessionOutputWriter,
) -> None:
    """Send a prompt to Fugu and stream the response."""

    content = build_content_parts(prompt, files) if files else prompt
    user_message = {"role": "user", "content": content}
    messages = [*history, user_message]
    
    # Initialize orchestration analyzer
    analyzer = OrchestrationAnalyzer(config, event_bus)
    
    console.print(f"\n[dim]> {prompt[:80]}{'...' if len(prompt) > 80 else ''}[/dim]")
    if files:
        names = ", ".join(path.name for path in files)
        console.print(f"[dim]Attachments: {names}[/dim]")
    console.print("[dim]Thinking...[/dim]", end="")
    output_writer.start_turn(prompt, files)
    response_parts: list[str] = []
    
    try:
        async for chunk in client.send(
            messages=messages,
            model=config.model.default,
            effort=config.model.reasoning_effort,  # type: ignore
            web_search=web_search,
        ):
            # Analyze chunk for orchestration patterns
            event = await analyzer.analyze_chunk(chunk)
            
            if chunk.type == "content":
                await event_bus.emit(
                    EventType.STREAM_CONTENT,
                    {"content": chunk.content},
                    source="vibe",
                )
                response_parts.append(chunk.content)
                output_writer.append_response(chunk.content)
                console.print(chunk.content, end="")
            elif chunk.type == "token_usage":
                await event_bus.emit(
                    EventType.STREAM_TOKEN_USAGE,
                    {
                        "input_tokens": chunk.token_usage.input_tokens,
                        "output_tokens": chunk.token_usage.output_tokens,
                        "orchestration_tokens": chunk.token_usage.orchestration_tokens,
                        "total_tokens": chunk.token_usage.total_tokens,
                    },
                    source="vibe",
                )
                orch = chunk.token_usage.orchestration_tokens
                if orch > 0:
                    console.print(f"\n[dim](orch: {orch} tokens)[/dim]")
                    
    except Exception as e:
        console.print(f"\n[red]Error: {e}[/red]")
    finally:
        response = "".join(response_parts)
        if response:
            history.append(user_message)
            history.append({"role": "assistant", "content": response})
        await analyzer.finalize()
        output_writer.end_turn()
        console.print("\n")


async def _handle_command(
    cmd: str,
    task_manager: TaskManager,
    event_bus: EventBus,
    dashboard: OrchestrationDashboard | None,
    attached_files: list[Path],
) -> None:
    """Handle slash commands."""
    parts = cmd.split()
    command = parts[0].lower()
    
    if command in ("/quit", "/q", "/exit"):
        raise EOFError()
        
    elif command == "/status":
        status = await task_manager.status()
        console.print(f"\nRunning: {status['running']}, Queued: {status['queued']}")
        
    elif command == "/tasks":
        status = await task_manager.status()
        for task in status["tasks"]:
            icon = "🔄" if task['status'] == 'running' else "✅" if task['status'] == 'completed' else "⏳"
            console.print(f"  {icon} {task['name']} [{task['status']}]")

    elif command == "/attach":
        for raw_path in _command_args(cmd):
            path = Path(raw_path).expanduser().resolve()
            if not path.is_file():
                console.print(f"[red]Not a file:[/red] {raw_path}")
                continue
            if path not in attached_files:
                attached_files.append(path)
            console.print(f"[green]Attached:[/green] {path}")

    elif command == "/files":
        if not attached_files:
            console.print("[dim]No files attached.[/dim]")
        for index, path in enumerate(attached_files, start=1):
            console.print(f"  {index}. {path}")

    elif command == "/clear-files":
        attached_files.clear()
        console.print("[green]Cleared attached files.[/green]")
            
    elif command == "/help":
        console.print("\n[bold]Commands:[/bold]")
        console.print("  /quit, /q     - Exit session")
        console.print("  /attach PATH  - Attach a PDF, image, or file")
        console.print("  /files        - List attached files")
        console.print("  /clear-files  - Remove all attached files")
        console.print("  /status       - Show system status")
        console.print("  /tasks        - List active tasks")
        console.print("  /help         - Show this help")
        console.print("")


def _command_args(cmd: str) -> list[str]:
    try:
        return shlex.split(cmd)[1:]
    except ValueError as e:
        console.print(f"[red]Invalid command syntax:[/red] {e}")
        return []
