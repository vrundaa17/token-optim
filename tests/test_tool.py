# import pytest
# from adapters.mcp.server import call_tool

# @pytest.mark.anyio
# async def test():
#     result = await call_tool("search_tools",{"query": "read the contents of a file"})
#     for item in result:
#         print(item.text)

#     assert result
import asyncio, sys, os, json
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__))))

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER_PATH = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "adapters",
        "mcp",
        "server.py",
    )
)
VENV_PYTHON = sys.executable  
server_params = StdioServerParameters(
    command=VENV_PYTHON,
    args=[SERVER_PATH],
)

async def main():
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()


            tools = await session.list_tools()
            print(" TOOLS AVAILABLE ")
            for t in tools.tools:
                print(f"  - {t.name}")

  
            print("\n INDEXING ")
            result = await session.call_tool("index_document", {
                "file_path": "/tmp/test_policy.pdf",
                "doc_id": "policy_v1"
            })
            print(result.content[0].text)

            print("\n ASKING ")
            result = await session.call_tool("ask_document", {
                "query": "what is the late payment penalty",
                "doc_id": "policy_v1"
            })
            chunks = json.loads(result.content[0].text)
            print(f"Got {len(chunks)} chunks")
            for i, c in enumerate(chunks):
                print(f"\nChunk {i+1} (page {c['page']}):")
                print(c["text"][:300])

asyncio.run(main())