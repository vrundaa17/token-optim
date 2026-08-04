import pytest
from adapters.mcp.server import call_tool

@pytest.mark.anyio
async def test():
    result = await call_tool("search_tools",{"query": "read the contents of a file"})
    for item in result:
        print(item.text)

    assert result