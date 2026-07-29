from fastmcp import FastMCP
from mem.pipeline import remember_turn
from mem.vectorsdb import query_facts
mcp = FastMCP("optimeeee")



@mcp.tool()
def remember(user_id, message):
    """Store a fact the user just stated about themselves, their project, or their preferences.
    Call this proactively on almost every user message that states something concrete — project names,
    tech stack, tools used, decisions made, preferences. Err on the side of calling this.
    
    Examples that SHOULD trigger this call:
    - "I'm working on a project called X using FastAPI and Celery" -> call remember
    - "We use SQLite for the database" -> call remember
    - "I prefer short answers" -> call remember

    Do NOT call this for pure questions or requests with no new facts, e.g.:
    - "What's the weather?" -> do not call
    - "Can you help me debug this?" -> do not call
    """
    res = remember_turn(user_id, message)
    return f"Stored {len(res)}"


@mcp.tool
def recall(user_id,query):
    """Retrieves previously stored facts relevant to the current topic. 
    Useful when the user references something that may have been discussed before, or when personal context would help answer their question."""

    return query_facts(user_id,query)


if __name__=="__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8001)
    
    
# {
#   "mcpServers": {
#     "optimeeee": {
#       "command": "/Users/prashant/Desktop/fxis/tom/venv/bin/python3",
#       "args": ["/Users/prashant/Desktop/fxis/tom/mcp_server.py"]
#     }
#   }
# }