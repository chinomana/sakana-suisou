"""MCP integration for Fugu Vibe."""

from fugu_vibe.mcp.client import MCPClient, MCPError, MCPServer, MCPTool
from fugu_vibe.mcp.store import MCPConfigStore
from fugu_vibe.mcp.tools import MCPToolManager

__all__ = ["MCPClient", "MCPConfigStore", "MCPError", "MCPServer", "MCPTool", "MCPToolManager"]
