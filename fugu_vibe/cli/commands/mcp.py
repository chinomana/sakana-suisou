"""`fugu-vibe mcp` - manage Model Context Protocol servers."""

from __future__ import annotations

import asyncio
import shlex
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from fugu_vibe.mcp import MCPClient, MCPConfigStore, MCPServer

console = Console()


@click.group(name="mcp")
def mcp_command() -> None:
    """Manage workspace MCP server definitions."""


@mcp_command.command(name="add")
@click.argument("name")
@click.argument("command", nargs=-1, required=True)
@click.pass_context
def mcp_add(ctx: click.Context, name: str, command: tuple[str, ...]) -> None:
    """Add a stdio MCP server command."""
    store = MCPConfigStore(ctx.obj.get("workspace", Path.cwd()))
    argv = list(command)
    if len(argv) == 1:
        argv = shlex.split(argv[0])
    if not argv:
        raise click.ClickException("MCP command cannot be empty")
    store.add(MCPServer(name=name, command=argv[0], args=argv[1:]))
    console.print(f"[green]Added MCP server:[/green] {name}")


@mcp_command.command(name="list")
@click.pass_context
def mcp_list(ctx: click.Context) -> None:
    """List configured MCP servers."""
    store = MCPConfigStore(ctx.obj.get("workspace", Path.cwd()))
    table = Table(title="MCP Servers")
    table.add_column("Name")
    table.add_column("Command")
    table.add_column("Args")
    for server in store.list_servers():
        table.add_row(server.name, server.command, " ".join(server.args))
    console.print(table)


@mcp_command.command(name="remove")
@click.argument("name")
@click.pass_context
def mcp_remove(ctx: click.Context, name: str) -> None:
    """Remove a configured MCP server."""
    store = MCPConfigStore(ctx.obj.get("workspace", Path.cwd()))
    if store.remove(name):
        console.print(f"[green]Removed MCP server:[/green] {name}")
    else:
        raise click.ClickException(f"Unknown MCP server: {name}")


@mcp_command.command(name="tools")
@click.argument("name")
@click.pass_context
def mcp_tools(ctx: click.Context, name: str) -> None:
    """Connect to a server and list its advertised tools."""
    store = MCPConfigStore(ctx.obj.get("workspace", Path.cwd()))
    server = store.get(name)
    if server is None:
        raise click.ClickException(f"Unknown MCP server: {name}")
    tools = asyncio.run(_list_tools(server))
    table = Table(title=f"MCP Tools: {name}")
    table.add_column("Name")
    table.add_column("Description")
    for tool in tools:
        table.add_row(tool.name, tool.description)
    console.print(table)


async def _list_tools(server: MCPServer):
    async with MCPClient(server) as client:
        return await client.list_tools()
