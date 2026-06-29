"""
`fugu-vibe attach` - Attach to a running task to view live output.
"""

from __future__ import annotations

import asyncio

import click
from rich.console import Console

from fugu_vibe.api.client import FuguClient
from fugu_vibe.core.event_bus import EventBus, EventType
from fugu_vibe.core.task_manager import TaskManager

console = Console()


@click.command()
@click.argument("task_id")
@click.pass_context
def attach_command(ctx: click.Context, task_id: str) -> None:
    """
    🔗 Attach to a running task and view live output.

    Similar to `docker attach` - connects to a running task
    to see its live streaming output.

    Examples:
        fugu-vibe attach <task-id>
    """
    config = ctx.obj["config"]
    asyncio.run(_attach(config, task_id))


async def _attach(config, task_id: str) -> None:
    event_bus = EventBus()
    await event_bus.start()

    client = FuguClient(config)
    task_manager = TaskManager(config, client, event_bus)
    await task_manager.start()

    try:
        # Check task exists
        status = await task_manager.status(task_id)
        if "error" in status:
            console.print(f"[red]Task not found: {task_id}[/red]")
            return

        task_status = status.get("status", "unknown")

        if task_status in ("completed", "failed", "cancelled"):
            console.print(f"[yellow]Task is already {task_status}[/yellow]")
            if status.get("output"):
                console.print("\nOutput:")
                console.print(status["output"])
            return

        console.print(f"[green]Attached to {task_id}[/green]")
        console.print("[dim]Press Ctrl+C to detach\n[/dim]")
        if status.get("output"):
            console.print(status["output"], end="")

        # Listen for output events
        output_buffer = []

        def on_content(event):
            if event.data.get("task_id") != task_id:
                return
            content = event.data.get("content", "")
            output_buffer.append(content)
            console.print(content, end="")

        event_bus.on(EventType.STREAM_CONTENT, on_content)

        # Wait for task to complete
        while True:
            status = await task_manager.status(task_id)
            if status.get("status") in ("completed", "failed", "cancelled"):
                break
            await asyncio.sleep(0.5)

        console.print(f"\n\n[dim]Task {status['status']}.[/dim]")

    except KeyboardInterrupt:
        console.print("\n[yellow]Detached[/yellow]")
    finally:
        await task_manager.close()
        await event_bus.close()
        await client.close()
