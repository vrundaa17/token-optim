import sys,os
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, project_root)
import asyncio
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.server.models import InitializationOptions
from mcp.server import NotificationOptions 
from mcp.types import Tool, TextContent

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from core.tool import select_relevant_tools


app = Server("tokennnnn")
_cached_tools=None

FILESYSTEM_SERVER_PARAMS = StdioServerParameters(
    command="npx",
    args=["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
)

async def get_tools():
    global _cached_tools
    if _cached_tools is None:
        async with stdio_client(FILESYSTEM_SERVER_PARAMS) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools_result = await session.list_tools()
                _cached_tools = tools_result.tools
    return _cached_tools


SEARCH_TOOL = Tool(
    name="search_tools",
    description="Searches a catalog of file-related tools (read, write, list, search) and executes the best match for a given task and target path.",
    inputSchema={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "What you're trying to do, e.g. 'read a file'"},
            "path": {"type": "string", "description": "The file or directory path involved, if any"},
        },
        "required": ["query"],
    },
)

_currently_relevant_tools = []
_currently_relevant_tools = []

@app.list_tools()
async def list_tools():
    if _currently_relevant_tools:
        print(f"[SERVER] returning narrowed set: {[t.name for t in _currently_relevant_tools]}", file=sys.stderr)
        return [SEARCH_TOOL] + _currently_relevant_tools
    print(f"[SERVER] returning only search_tools (no active search yet)", file=sys.stderr)
    return [SEARCH_TOOL]

@app.call_tool()
async def call_tool(name, arguments):
    if name == "search_tools":
        all_tools = await get_tools()
        query = arguments["query"]
        tool_dicts = [{"function": {"name": t.name, "description": t.description}} for t in all_tools]
        relevant = select_relevant_tools(tool_dicts, query, top_k=1)
        if not relevant:
            return [TextContent(type="text", text="No relevant tool found for this request.")]

        best_tool_name = relevant[0]["function"]["name"]
        print(f"[SERVER] search_tools('{query}') → auto-executing: {best_tool_name}", file=sys.stderr)

        real_args = {k: v for k, v in arguments.items() if k != "query"}

        server_params = StdioServerParameters(command="npx", args=["-y", "@modelcontextprotocol/server-filesystem", "/tmp"])
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(best_tool_name, real_args)
                return result.content

    print(f"[Server] {name} with {arguments}", file=sys.stderr)
    server_params = StdioServerParameters(command="npx", args=["-y", "@modelcontextprotocol/server-filesystem", "/tmp"])
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(name, arguments)
            return result.content
        
        
async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,write_stream,InitializationOptions(
                server_name="tokennnnn",
                server_version="0.1",
                capabilities=app.get_capabilities(
                    notification_options=NotificationOptions(tools_changed=True),   
                    experimental_capabilities={},
            )
        ))

if __name__ == "__main__":
    asyncio.run(main())
    
# {
#   "mcpServers": {
#     "token-optimizer": {
#       "command": "/Users/prashant/Desktop/fxis/tom/venv/python3",
#       "args": ["/Users/prashant/Desktop/fxis/tom/adapters/mcp_router/server.py"]
#     }
#   }
# }