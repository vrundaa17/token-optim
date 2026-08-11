import sys, os
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, project_root)

import asyncio
import logging
from contextlib import asynccontextmanager
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from fastmcp import FastMCP

from core.trim import trim_text_response
from core.tool_selection import select_relevant_tools
from core.cache import check_cache, store_answer
# from core.audit import count_tokens
from core.document_search import search_doc, index_doc, search_all_doc,index_folder  as _index_folder
# from adapters.extenstion.db import get_connection, insert_audit_log

# logging.basicConfig(level=logging.INFO, stream=sys.stderr,
#     format="%(asctime)s [%(levelname)s] %(message)s")

logging.basicConfig(
    level=logging.INFO,
    handlers=[
        logging.FileHandler(os.path.join(project_root, "server.log")),
        logging.StreamHandler(sys.stderr)
    ],
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("token")


_cached_tools = None
_tool_server_map: dict[str, StdioServerParameters] = {}
_tool_schema_map: dict[str,dict]={}
# _db_conn = get_connection()
_session_run_id = "live_it_is"
ALLOWED_DIR = os.getenv("ALLOWED_DIR", "/tmp")

DOWNSTREAM_SERVERS = [
    StdioServerParameters(
        command="npx",
        args=["-y", "@modelcontextprotocol/server-filesystem", ALLOWED_DIR],
    ),
    StdioServerParameters(
        command="npx",
        args=["-y", "@modelcontextprotocol/server-memory"],
    ),
]


# def #_audit(stage, message, prompt_text, completion_text=""):
#     prompt_tokens = count_tokens(prompt_text)
#     completion_tokens = count_tokens(completion_text) if completion_text else 0
#     insert#_audit_log(_db_conn, _session_run_id, stage, prompt_tokens, completion_tokens, message=message)
#     return prompt_tokens, completion_tokens


async def discover_tools_from_server(server_params: StdioServerParameters) -> list:
    try:
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.list_tools()
                logger.info(f"Discovered {len(result.tools)} tools from {server_params.args}")
                return result.tools
    except Exception as e:
        logger.error(f"Failed to discover tools from {server_params.args}: {e}")
        return []


def build_args_schema(schema,query,path):
    if not schema or "properties" not in schema:
        return {}
    
    props = schema["properties"]
    required = schema.get("required", [])
    args = {}
    for field_name, field_info in props.items():
        field_type = field_info.get("type", "string")
        
        if field_type=="string":
            if field_name in ("path", "source", "file_path"):
                args[field_name] = path if path else query
            elif field_name in ("query", "text", "content","message","input"):
                args[field_name] = query
            elif field_name in ("pattern",):
                args[field_name] = query
            elif field_name in required:
                args[field_name]= query
                
        elif field_type == "array":
            if field_name in required:
                args[field_name] = [query]
        
        elif field_type == "object":
            if field_name in required:
                args[field_name] = {}
    
    return args



async def get_tools():
    global _cached_tools, _tool_server_map, _tool_schema_map
    if _cached_tools is None:
        results = await asyncio.gather(
            *[discover_tools_from_server(s) for s in DOWNSTREAM_SERVERS]
        )
        _cached_tools = []
        _tool_server_map = {}
        _tool_schema_map = {}
        for server_params, server_tools in zip(DOWNSTREAM_SERVERS, results):
            for t in server_tools:
                _cached_tools.append(t)
                _tool_server_map[t.name] = server_params
                _tool_schema_map[t.name] = t.inputSchema or {}
        
        tool_dicts = [{"function": {"name": t.name, "description": t.description}} for t in _cached_tools]
        from core.tool_selection import index_tools
        index_tools(tool_dicts)
        logger.info(f"Tools indexed into chroma")
    return _cached_tools


async def _run_downstream_tool(name: str, arguments: dict):
    server_params = _tool_server_map.get(name)
    if not server_params:
        raise ValueError(f"No server found for tool '{name}'")
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            return await session.call_tool(name, arguments)



@asynccontextmanager
async def lifespan(server):
    logger.info("Starting tool discovery...")
    await get_tools()
    logger.info(f"Tool discovery complete, {len(_cached_tools)} tools ready")
    yield


app = FastMCP("token", lifespan=lifespan)


@app.tool(description="Use this for ANY task involving local files, folders, or documents on the user's computer.")
async def find_tool(query: str, path: str = "") -> str:
    logger.info(f"find_tool called | query: {query}")
    if not query.strip():
        return "Error: query is required"

    cached, score = check_cache(query)
    if cached:
        #_audit("cache_hit", query, query, cached)
        logger.info(f"CACHE HIT | sim={score:.3f}")
        return cached

    logger.info(f"CACHE MISS | sim={score:.3f}")
    tools = await get_tools()
    tool_dicts = [{"function": {"name": t.name, "description": t.description}} for t in tools]
    selected = select_relevant_tools(tool_dicts, query, top_k=1)

    if not selected:
        return "No matching tool found."

    tool_name = selected[0]["function"]["name"]
    schema = _tool_schema_map.get(tool_name, {})
    args = build_args_schema(schema, query, path)
    logger.info(f"selected: {tool_name} | args: {args}")

    try:
        result = await _run_downstream_tool(tool_name, args)
        answer = result.content[0].text if result.content else ""
        answer, original_tokens, final_tokens = trim_text_response(answer)
        if original_tokens != final_tokens:
            logger.info(f"[TRIMMED] | {original_tokens} | {final_tokens} tokens | saved {original_tokens - final_tokens}")

        #_audit("tool_execution", query, query, answer)
        if answer:
            store_answer(query, answer)
        return answer
    except Exception as e:
        logger.error(f"Tool execution failed: {e}")
        return f"Tool execution failed: {str(e)}"



@app.tool(description="Index and summarise any PDF or document file from a local file path on the user's computer.")
async def index_document(file_path: str, doc_id: str) -> str:
    chunks = index_doc(file_path, doc_id)
    message = f"Indexed {doc_id} | {chunks} chunks stored."
    #_audit("index_document", doc_id, file_path, message)
    return message


@app.tool(description="Answer questions about any PDF or document file that has been indexed from the user's local computer.")
async def ask_document(query: str, doc_id: str, top_k: int = 3) -> str:
    cache_key = f"{doc_id}:{query}"
    cached, _ = check_cache(cache_key)
    if cached:
        #_audit("rag_cache_hit", query,cache_key, cached)
        return cached

    results = search_doc(query, doc_id, top_k)
    answer = "\n\n".join([f"[Page {r.get('page', '?')}]\n{r['text']}" for r in results])
    #_audit("rag_search", query, query, answer)
    store_answer(cache_key, answer)
    return answer


@app.tool(description="Search across ALL indexed documents and return the most relevant chunks.")
async def search_all_documents(query: str, top_k: int = 3) -> str:
    
    cache_key = f"all:{query}"
    cached, score = check_cache(cache_key)
    if cached:
        #_audit("rag_cache_hit", query, cache_key, cached)
        return cached
    
    results = search_all_doc(query, top_k)
    if not results:
        return "No results found across any indexed documents."
    
    answer="\n\n".join([
        f"[Doc: {r.get('doc_id')} |  Page {r.get('page', '?')}]\n{r['text']}"
        for r in results
    ])
    
    #_audit("rag_search_all",query,query,answer)
    store_answer(cache_key,answer)
    return answer



@app.tool(description="Index all PDF files in a folder so they can be searched later.")
async def index_documents_folder(folder_path: str) -> str:
    try:
        results = _index_folder(folder_path)
        if not results:
            return f"No PDF files found in {folder_path}"
        
        summary = "\n".join([f"  {doc_id}: {chunks} chunks" for doc_id, chunks in results.items()])
        message = f"Indexed {len(results)} documents from {folder_path}:\n{summary}"
        #_audit("index_folder", folder_path, folder_path, message)
        return message
    except Exception as e:
        return f"Error: {str(e)}"
    
    
@app.prompt(description="Sets up Claude to automatically use the token optimizer tools for documents and file operations.")
def token_optimizer_prompt() -> str:
    return """
        You have access to a token-optimized MCP server with these tools:
        - find_tool: Use this for ANY task involving files, memory, or data retrieval
        - index_document: Use this before asking questions about a PDF
        - ask_document: Use this to query an indexed document
        - search_all_documents: Use this to search across all indexed documents
        - index_documents_folder: Use this to index all PDFs in a folder

        Always prefer these tools over answering from memory when the task involves documents or file operations.
    """
    
if __name__ == "__main__":
    app.run(transport="stdio")