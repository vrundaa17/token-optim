import sys, os
_file_dir = os.path.dirname(os.path.abspath(__file__))
_src_dir = os.path.abspath(os.path.join(_file_dir, ".."))
_project_root = os.path.abspath(os.path.join(_file_dir, "..", ".."))
sys.path.insert(0, _src_dir)
sys.path.insert(0, _project_root)
import asyncio,json
import logging
from contextlib import asynccontextmanager
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from fastmcp import FastMCP

from core.client import fill_args_llm
from core.trim import trim_text_response,count_tokens
from core.tool_selection import select_relevant_tools,index_tools
from core.cache import check_cache, store_answer
from core.document_search import search_doc, index_doc,list_index_doc, search_all_doc,index_folder  as _index_folder
from core.db import get_connection, init_db, insert_event

# logging.basicConfig(level=logging.INFO, stream=sys.stderr,
#     format="%(asctime)s [%(levelname)s] %(message)s")

logging.basicConfig(
    level=logging.INFO,
    handlers=[
        logging.FileHandler(os.path.join(_project_root, "server.log")),
        logging.StreamHandler(sys.stderr)
    ],
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("token")


_cached_tools = None
_tool_server_map: dict[str, StdioServerParameters] = {}
_tool_schema_map: dict[str, dict] = {}
_persistent_sessions: dict[str, ClientSession] = {}
_session_contexts = []

ALLOWED_DIR = os.getenv("ALLOWED_DIR", os.path.expanduser("~"))
if not os.path.isdir(ALLOWED_DIR):
    logger.warning(f"[CONFIG] ALLOWED_DIR '{ALLOWED_DIR}' does not exist, falling back to home directory")
    ALLOWED_DIR = os.path.expanduser("~")
logger.info(f"[CONFIG] Filesystem MCP serving: {ALLOWED_DIR}")



def _load_from_claude_config():
    paths = [
        os.path.expanduser("~/Library/Application Support/Claude/claude_desktop_config.json"),
        os.path.expandvars(r"%APPDATA%\Claude\claude_desktop_config.json"),
        os.path.expanduser("~/.config/Claude/claude_desktop_config.json"),
    ]
    SKIP = {"token", "wick"}
    
    for p in paths:
        if not os.path.exists(p):
            continue
        
        backup_path = p.replace(".json", "") + ".token_optim_backup.json"
    
        if os.path.exists(backup_path):
            logger.info(f"[CHANGE_CLAUDE] backup found — loading servers from backup")
            with open(backup_path) as f:
                backup_config = json.load(f)
            # also check live config for newly added servers
            with open(p) as f:
                live_config = json.load(f)
            # merge: backup servers + any new ones in live config not in SKIP
            backup_servers = backup_config.get("mcpServers", {})
            live_servers = live_config.get("mcpServers", {})
            # only add genuinely new servers not already in backup
            new_servers = {k: v for k, v in live_servers.items() if k not in backup_servers}
            merged = {**backup_servers, **new_servers}
            backup_config["mcpServers"] = merged
            with open(backup_path, "w") as f:
                json.dump(backup_config, f, indent=2)
            servers = []
            for name, s in merged.items():
                if name in SKIP:
                    continue
                servers.append(StdioServerParameters(
                    command=s["command"],
                    args=s.get("args", []),
                    env=s.get("env", {}) or {}
                ))
                logger.info(f"[CHANGE_CLAUDE] loaded: {name}")
            return servers, p, backup_path
                
        # no backup — first run, do the CHANGE_CLAUDE
        with open(p) as f:
            config = json.load(f)
        
        try:
            with open(backup_path, "w") as f:
                json.dump(config, f, indent=2)
            logger.info(f"[CHANGE_CLAUDE] backed up claude config")
        except Exception as e:
            logger.error(f"[CHANGE_CLAUDE] backup failed: {e} — aborting")
            return [], None, None
        
        servers = []
        kept = {}
        for name, s in config.get("mcpServers", {}).items():
            if name in SKIP:
                kept[name] = s
            else:
                servers.append(StdioServerParameters(
                    command=s["command"],
                    args=s.get("args", []),
                    env=s.get("env", {}) or {}
                ))
                logger.info(f"[CHANGE_CLAUDE]  MCP: {name}")
        
        config["mcpServers"] = kept
        with open(p, "w") as f:
            json.dump(config, f, indent=2)
        logger.info(f"[CHANGE_CLAUDE] rewrote claude config — {len(servers)} MCPs ")
        
        return servers, p, backup_path
    
    logger.warning("[CHANGE_CLAUDE] claude config not found")
    return [], None, None


DOWNSTREAM_SERVERS, _config_path, _backup_path = _load_from_claude_config()
            
# DOWNSTREAM_SERVERS = [
#     StdioServerParameters(
#         command="npx",
#         args=["-y", "@modelcontextprotocol/server-filesystem", ALLOWED_DIR],
#     ),
#     StdioServerParameters(
#         command="npx",
#         args=["-y", "@modelcontextprotocol/server-memory"],
#     ),
# ]

_restored = False
def _restore_claude_config(backup_path, config_path):
    global _restored
    if _restored:
        logger.info("[RESTORE] already restored, skipping")
        return
    if not backup_path or not os.path.exists(backup_path):
        return
    _restored = True
    with open(backup_path) as f:
        config = json.load(f)
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)
    os.remove(backup_path)
    logger.info("[RESTORE] restored claude config from backup")
    # ,
    # "filesystem": {
    #   "command": "npx",
    #   "args": ["-y", "@modelcontextprotocol/server-filesystem", "/Users/prashant"]
    # },
    # "memory": {
    #   "command": "npx",
    #   "args": ["-y", "@modelcontextprotocol/server-memory"]
    # }



async def discover_tools_from_server(server_params: StdioServerParameters, retries: int = 2) -> list:
    for attempt in range(retries):
        try:
            async with stdio_client(server_params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.list_tools()
                    logger.info(f"[DISCOVERY] {len(result.tools)} tools from {server_params.args}")
                    return result.tools
        except Exception as e:
            logger.error(f"[DISCOVERY] attempt {attempt + 1} failed for {server_params.args}: {e}")
            if attempt < retries - 1:
                await asyncio.sleep(2)
            else:
                logger.error(f"[DISCOVERY] giving up on {server_params.args} after {retries} attempts")
    return []

def _schema_savings():
    full = sum(count_tokens(json.dumps(s)) for s in _tool_schema_map.values())
    selected = 20
    return full, selected, full - selected


# def build_args_schema(schema,query,path):
#     if not schema or "properties" not in schema:
#         return {}
    
#     props = schema["properties"]
#     required = schema.get("required", [])
#     args = {}
#     confident =True
    
#     for field_name, field_info in props.items():
#         field_type = field_info.get("type", "string")
        
#         if field_type=="string":
#             if field_name in ("path", "source", "file_path"):
#                 args[field_name] = path if path else query
#             elif field_name in ("query", "text", "content","message","input"):
#                 args[field_name] = query
#             elif field_name in ("pattern",):
#                 args[field_name] = query
#             elif field_name in required:
#                 confident=False
                
#         elif field_type == "array":
#             if field_name in required:
#                 args[field_name] = [query]
        
#         elif field_type == "object":
#             if field_name in required:
#                 confident=False
                
#     for field_name in required:
#         if field_name not in args:
#             confident = False
#     return args,confident


async def refresh_tools():
    global _cached_tools
    _cached_tools = None
    await get_tools()
    logger.info("[TOOLS] tool cache refreshed")


async def get_tools():
    global _cached_tools, _tool_server_map, _tool_schema_map
    if _cached_tools is None:
        results = await asyncio.gather(
            *[discover_tools_from_server(s) for s in DOWNSTREAM_SERVERS],
            return_exceptions=True
        )
        _cached_tools = []
        _tool_server_map = {}
        _tool_schema_map = {}
        
        for server_params, server_tools in zip(DOWNSTREAM_SERVERS, results):
            if isinstance(server_tools, Exception):
                logger.error(f"[GET_TOOLS] server {server_params.args} raised exception: {server_tools}")
                continue
            if not server_tools:
                logger.warning(f"[GET_TOOLS] server {server_params.args} returned no tools, skipping")
                continue
            for t in server_tools:
                _cached_tools.append(t)
                _tool_server_map[t.name] = server_params
                _tool_schema_map[t.name] = t.inputSchema or {}
        
        if not _cached_tools:
            logger.error("[GET_TOOLS] no tools discovered from any downstream server — check if npx is available and servers are reachable")
        else:
            tool_dicts = [{"function": {"name": t.name, "description": t.description}} for t in _cached_tools]
            from core.tool_selection import index_tools
            index_tools(tool_dicts)
            logger.info(f"[GET_TOOLS] {len(_cached_tools)} tools indexed into chroma")
    
    return _cached_tools


async def _run_downstream_tool(name: str, arguments: dict):
    server_params = _tool_server_map.get(name)
    if not server_params:
        raise ValueError(f"No server mapped for tool '{name}' — it may have been removed from a downstream server")
    
    session = _persistent_sessions.get(str(server_params.args))
    if session:
        try:
            logger.info(f"[SESSION] reusing persistent session for {name}")
            return await session.call_tool(name, arguments)
        except Exception as e:
            logger.warning(f"[SESSION] persistent session failed for {name}: {e} — falling back to new session")
    
    # fallback — spawn fresh session
    try:
        logger.info(f"[SESSION] spawning fresh session for {name}")
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                return await session.call_tool(name, arguments)
    except Exception as e:
        logger.error(f"[SESSION] fresh session also failed for {name}: {e}")
        raise RuntimeError(f"Tool '{name}' is unreachable — both persistent and fresh sessions failed") from e


@asynccontextmanager
async def lifespan(server):
    global _persistent_sessions, _session_contexts
    logger.info("Starting tool discovery...")
    await get_tools()
    logger.info(f"Tool discovery complete, {len(_cached_tools)} tools ready")
    logger.info(f"[STARTUP]  Ready | tools: {len(_cached_tools)} | sessions: {len(_persistent_sessions)}")
    # open persistent sessions
    for server_params in DOWNSTREAM_SERVERS:
        try:
            ctx = stdio_client(server_params)
            read, write = await ctx.__aenter__()
            session = ClientSession(read, write)
            await session.__aenter__()
            await session.initialize()
            _persistent_sessions[str(server_params.args)] = session
            _session_contexts.append((ctx, session))
            logger.info(f"Persistent session opened for {server_params.args}")
        except Exception as e:
            logger.error(f"Failed to open persistent session for {server_params.args}: {e}")
    
    # periodic tool refresh task
    async def _refresh_loop():
        while True:
            await asyncio.sleep(1800) 
            try:
                await refresh_tools()
            except Exception as e:
                logger.error(f"[TOOLS] refresh failed: {e}")
    refresh_task = asyncio.create_task(_refresh_loop())
    
    import signal,atexit

    def _emergency_restore():
        if _backup_path and _config_path:
            _restore_claude_config(_backup_path, _config_path)

    atexit.register(_emergency_restore)

    def _signal_handler(signum, frame):
        logger.info(f"[SIGNAL] received {signum}, restoring config before exit")
        _emergency_restore()
        sys.exit(0)

    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)

    yield
    
    refresh_task.cancel()
    try:
        await refresh_task
    except asyncio.CancelledError:
        pass
    
    # clean up sessions
    for ctx, session in _session_contexts:
        try:
            await session.__aexit__(None, None, None)
            await ctx.__aexit__(None, None, None)
        except Exception as e:
            logger.warning(f"Error closing session: {e}")
    _restore_claude_config(_backup_path, _config_path)
   
    logger.info("All persistent sessions closed")


app = FastMCP("token", lifespan=lifespan)



#------------------------------------------------------------------------------------------------------------------------

#---------------------------------------------------------------------------------------------------------------------------

@app.tool(description="Use this for any file system task — listing files, reading files, searching files, writing files. Pass the full natural language request as the query.")
async def find_tool(query: str) -> str:
    logger.info(f"find_tool called | query: {query}")
    
    if not query or not query.strip():
        return "Error: query cannot be empty. Please describe what file operation you want to perform."

    cached, score = check_cache(query,"find_tool")
    if cached:
        logger.info(f"CACHE HIT | sim={score:.3f}")
        
        asyncio.create_task(asyncio.to_thread(lambda: insert_event( tool_name="find_tool", query=query, cache_hit=1, cache_similarity= score, success=1)))
        return cached

    logger.info(f"CACHE MISS | sim={score:.3f}")
    tools = await get_tools()
    tool_dicts = [{"function": {"name": t.name, "description": t.description}} for t in tools]
    selected = select_relevant_tools(tool_dicts, query, top_k=1)

    if not selected:
        logger.warning(f"[TOOL SELECT] no confident tool match for: '{query}'")
        asyncio.create_task(asyncio.to_thread(lambda: insert_event( tool_name='find_tool',query=query, cache_hit=0, cache_similarity= score, success=0)))
        return "No matching tool found."

    tool_name = selected[0]["function"]["name"]
    schema = _tool_schema_map.get(tool_name, {})
    
    full_schema_token = sum(count_tokens(json.dumps(s)) for s in _tool_schema_map.values())
    selected_schema_tokens = count_tokens(json.dumps(schema))
    schema_token_saved = full_schema_token - selected_schema_tokens
    logger.info(f"schema tokens | full={full_schema_token} | selected={selected_schema_tokens} | saved={schema_token_saved}")
    
    args = fill_args_llm(query, schema)
    if not args:
        logger.warning(f"[ARGS] LLM failed for {tool_name}")
        args = {}
    logger.info(f"selected: {tool_name} | args: {args}")

    for attempt in range(2):
        try:
            result = await _run_downstream_tool(tool_name, args)
            answer = result.content[0].text if result.content else ""
            
            if not answer.strip():
                logger.warning(f"[RETRY] attempt {attempt + 1} — empty response from {tool_name}")
                if attempt == 0:
                    logger.info(f"[RETRY] refilling args with LLM before retry")
                    llm_args = fill_args_llm(query, schema)
                    if llm_args:
                        args = llm_args
                    continue
                else:
                    asyncio.create_task(asyncio.to_thread(lambda: insert_event( tool_name=tool_name, query=query,
                                 cache_hit=0, cache_similarity=score,
                                 schema_tokens_full=full_schema_token,
                                 schema_tokens_selected=selected_schema_tokens,
                                 schema_tokens_saved=schema_token_saved, success=0)))
                    return f"Tool '{tool_name}' returned no results for: {query}"
            
            answer, original_tokens, final_tokens = trim_text_response(answer)
            trim_saved = original_tokens - final_tokens
            if trim_saved > 0:
                logger.info(f"[TRIMMED] find_tool | {original_tokens} | {final_tokens} tokens | saved {trim_saved}")

            if answer:
                store_answer(query, answer)

            asyncio.create_task(asyncio.to_thread(lambda: insert_event( tool_name=tool_name, query=query,
                        cache_hit=0, cache_similarity=score,
                         tokens_before_trim=original_tokens, tokens_after_trim=final_tokens,
                         trim_saved=trim_saved,
                         schema_tokens_full=full_schema_token,
                         schema_tokens_selected=selected_schema_tokens,
                         schema_tokens_saved=schema_token_saved, success=1)))
            return answer
        
        except Exception as e:
            logger.error(f"[RETRY] attempt {attempt + 1} failed for {tool_name}: {e}")
            if attempt == 0:
                continue
            asyncio.create_task(asyncio.to_thread(lambda: insert_event( tool_name=tool_name, query=query,
                         cache_hit=0, success=0)))
            return f"Could not complete the request — {tool_name} failed after 2 attempts."
    
    return f"Could not complete the request for: {query}"


#------------------------------------------------------------------------------------------------------------------------

#---------------------------------------------------------------------------------------------------------------------------
@app.tool(description="CALL THIS FIRST before answering ANY question that might relate to a document, PDF, or any topic a user mentions by name. If results come back with a matching doc_id, immediately call ask_document. Do not search the web, do not ask for clarification.")
async def list_indexed_documents():
    docs = list_index_doc()
    if not docs:
        return "No documents have been indexed yet. Use index_document to index a PDF first."
    lines = [f"- {doc_id} | {source}" for doc_id, source in docs.items()]
    result = "\n".join(lines)
    schema_full, schema_selected, schema_saved = _schema_savings()
    asyncio.create_task(asyncio.to_thread(lambda: insert_event(
        tool_name="list_indexed_documents", query="list docs",
        schema_tokens_full=schema_full,
        schema_tokens_selected=schema_selected,
        schema_tokens_saved=schema_saved,
        success=1
    )))
    return f"Indexed documents ({len(docs)}):\n{result}"
    

#------------------------------------------------------------------------------------------------------------------------

#---------------------------------------------------------------------------------------------------------------------------
@app.tool(description="Index a PDF file before asking questions about it. Always call this first when the user wants to query a PDF they haven't indexed yet. Requires a file path and a short doc_id name.")
async def index_document(file_path: str, doc_id: str) -> str:
    logger.info(f"[INDEX] indexing request for file - {file_path} | doc_id : {doc_id}")
    try:
        chunks = index_doc(file_path, doc_id)
        message = f"Successfully indexed '{doc_id}' | {chunks} chunks stored from {file_path}"
        logger.info(f"[INDEX] done | {doc_id} | {chunks} chunks")
        schema_full, schema_selected, schema_saved = _schema_savings()
        asyncio.create_task(asyncio.to_thread(lambda: insert_event(
            tool_name="index_document", query=file_path,
            schema_tokens_full=schema_full,
            schema_tokens_selected=schema_selected,
            schema_tokens_saved=schema_saved,
            success=1
        )))
        return message
        #_audit("index_document", doc_id, file_path, message)

    except FileNotFoundError as e:
        logger.error(f"[INDEX] file not found: {e}")
        return f"Error: File not found — {file_path}. Please check the path and try again."
    except ValueError as e:
        logger.error(f"[INDEX] validation error: {e}")
        return f"Error: {e}"
    except Exception as e:
        logger.error(f"[INDEX] unexpected error for {file_path} :{e}")
        return f"Error : Could not index {file_path} - {str(e)}"



#------------------------------------------------------------------------------------------------------------------------

#---------------------------------------------------------------------------------------------------------------------------
@app.tool(description="Answer questions about indexed documents. If list_indexed_docs returned any doc_id that relates to the user's query, call this immediately with that doc_id. Never use web search when an indexed document exists.")
async def ask_document(query: str, doc_id: str, top_k: int = 3) -> str:
    cache_key = f"{doc_id}:{query}"
    cached, score = check_cache(cache_key,"ask_document")
    if cached:
        asyncio.create_task(asyncio.to_thread(lambda: insert_event( tool_name="ask_document", query=query,
                     doc_id=doc_id, cache_hit=1, cache_similarity=score, success=1)))
        return cached

    results = search_doc(query, doc_id, top_k)
    answer = "\n\n".join([f"[Page {r.get('page', '?')}]\n{r['text']}" for r in results])
    answer, original_tokens, final_tokens = trim_text_response(answer)
    trim_saved = original_tokens - final_tokens
    if trim_saved > 0:
        logger.info(f"[TRIMMED] ask_document | {original_tokens} | {final_tokens} | saved {trim_saved}")

    store_answer(cache_key, answer)
    schema_full, schema_selected, schema_saved = _schema_savings()
    asyncio.create_task(asyncio.to_thread(lambda: insert_event(
        tool_name="ask_document", query=query,
        doc_id=doc_id, cache_hit=0, cache_similarity=score,
        tokens_before_trim=original_tokens, tokens_after_trim=final_tokens,
        trim_saved=trim_saved,
        schema_tokens_full=schema_full,        # add this
        schema_tokens_selected=schema_selected, # add this
        schema_tokens_saved=schema_saved,       # add this
        success=1
    )))
    return answer



#------------------------------------------------------------------------------------------------------------------------

#---------------------------------------------------------------------------------------------------------------------------
@app.tool(description="Search across ALL previously indexed PDFs when the user asks a question but doesn't specify which document. Use this for broad document queries with no specific doc_id.")
async def search_all_documents(query: str, top_k: int = 3) -> str:
    cache_key = f"all:{query}"
    cached, score = check_cache(cache_key,"search_all_documents")
    if cached:
        asyncio.create_task(asyncio.to_thread(lambda: insert_event( tool_name="search_all_documents", query=query,
                     cache_hit=1, cache_similarity=score, success=1)))
        return cached
    
    results = search_all_doc(query, top_k)
    if not results:
        return "No results found across any indexed documents."
    
    answer = "\n\n".join([
        f"[Doc: {r.get('doc_id')} | Page {r.get('page', '?')}]\n{r['text']}"
        for r in results
    ])
    
    answer, original_tokens, final_tokens = trim_text_response(answer)
    trim_saved = original_tokens - final_tokens
    if trim_saved > 0:
        logger.info(f"[TRIMMED] search_all_documents | {original_tokens} | {final_tokens} | saved {trim_saved}")

    if answer:
        store_answer(cache_key, answer)
    schema_full, schema_selected, schema_saved = _schema_savings()
    asyncio.create_task(asyncio.to_thread(lambda: insert_event( tool_name="search_all_documents", query=query,
                 cache_hit=0, cache_similarity=score,
                 tokens_before_trim=original_tokens, tokens_after_trim=final_tokens,
                 trim_saved=trim_saved,schema_tokens_full=schema_full,        # add this
    schema_tokens_selected=schema_selected, # add this
    schema_tokens_saved=schema_saved, success=1)))
    return answer


#---------------------------------------------------------------------------------------------------------------------------

#---------------------------------------------------------------------------------------------------------------------------
@app.tool(description="Index all PDF files inside a folder at once. Use this when the user wants to index an entire directory of PDFs rather than a single file.")
async def index_documents_folder(folder_path: str) -> str:
    logger.info(f"[INDEX_FOLDER] request | folder: {folder_path}")
    if not folder_path or not folder_path.strip():
        return "Error: folder_path cannot be empty"
    if not os.path.exists(folder_path):
        return f"Error: Folder not found — {folder_path}. Please check the path."
    if not os.path.isdir(folder_path):
        return f"Error: {folder_path} is not a directory."
    
    try:
        results = _index_folder(folder_path)
        if not results:
            return f"No PDF files found in {folder_path}. Make sure the folder contains .pdf files."
        success = {k: v for k, v in results.items() if v > 0}
        failed = {k: v for k, v in results.items() if v == 0}
        
        lines = [f"     {doc_id}: {chunks} chunks" for doc_id, chunks in success.items()]
        if failed:
            lines += [f"    {doc_id}: failed to index" for doc_id in failed]
            
        message= f"Indexed {len(success)}/{len(results)} from {folder_path} : {"\n".join(lines)}"
        logger.info(f"[INDEX_FOLDER] done | {len(success)} success | {len(failed)} failed")
        #_audit("index_folder", folder_path, folder_path, message)
        schema_full, schema_selected, schema_saved = _schema_savings()
        asyncio.create_task(asyncio.to_thread(lambda: insert_event(
            tool_name="index_documents_folder", query=folder_path,
            schema_tokens_full=schema_full,
            schema_tokens_selected=schema_selected,
            schema_tokens_saved=schema_saved,
            success=1
        )))
        return message

    except Exception as e:
        logger.error(f"[INDEX_FOLDER] unexpected error: {e}")
        return f"Error: Could not index folder — {str(e)}"
    
    
    
#------------------------------------------------------------------------------------------------------------------------

#---------------------------------------------------------------------------------------------------------------------------
@app.prompt(description="Sets up Claude to automatically use the token optimizer tools for documents and file operations.")
def token_prompt() -> str:
    return """
        You have access to a token MCP server. ALWAYS use these tools for every request:
        - find_tool: for ANY file system operation — listing, reading, writing files
        - index_document: ALWAYS call this first before querying a PDF
        - ask_document: for questions about a specific already-indexed PDF
        - search_all_documents: for questions across all indexed PDFs
        - index_documents_folder: to index all PDFs in a folder at once

        NEVER answer file or document questions from memory — ALWAYS call the appropriate tool first.
        NEVER use find_tool for PDF questions.
        NEVER use ask_document without indexing first.
    """
#    
if __name__ == "__main__":
    app.run(transport="stdio")
    
    
    
    
