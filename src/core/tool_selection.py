from config import settings,PROJECT_ROOT
from core.client import _chroma_client, expand_query
from chromadb.utils import embedding_functions
import os
import logging; 
logger = logging.getLogger("token")
CHROMA_PATH = os.path.join(PROJECT_ROOT, "storage", "chroma_db")

_embedder = embedding_functions.SentenceTransformerEmbeddingFunction(model_name=settings.embedder)
_tools_indexed = False
_indexed_tool_names:set = set()

# ALIASES = {
#     "create_entities": "save a note store information remember something write something down create a memory",
#     "search_nodes": "find a note search memory look up information retrieve",
#     "read_graph": "show all notes list everything stored show memory",
#     "add_observations": "update a note add to existing note append information",
#     "open_nodes": "open a note read a specific note get a note",
# }


def _enrich_description(name: str, description: str) -> str:
    name_as_words = name.replace("_", " ").replace("-", " ").lower()
    enriched = f"{name_as_words} {description}".strip()
    return enriched


def index_tools(tools):
    global _tools_indexed,_indexed_tool_names
    collection = _chroma_client.get_or_create_collection(name="tools", embedding_function=_embedder)
    incoming_names = {t['function']['name'] for t in tools}
    
    removed = _indexed_tool_names - incoming_names
    if removed:
        collection.delete(ids=list(removed))
        logger.info(f"[TOOLS]  removed {len(removed)} from index: {removed}")
        
        
    enriched_docs = []
    for t in tools:
        name = t['function']['name']
        desc = t['function']['description']
        enriched_docs.append(_enrich_description(name, desc))
    
    collection.upsert(
        ids=[t['function']['name'] for t in tools],
        documents=enriched_docs,
        metadatas=[{"name": t['function']['name']} for t in tools],
    )

    _indexed_tool_names = incoming_names
    _tools_indexed = True
    logger.info(f"[TOOLS] indexed {len(tools)} tools dynamically")
    

TOOL_CONFIDENCE_THRESHOLD = 0.3

def select_relevant_tools(tools: list[dict], query: str, top_k: int = 2) -> list[dict]:
    global _tools_indexed
    if len(tools) <= top_k:
        return tools
    
    normalized = expand_query(query, tools)

    collection = _chroma_client.get_or_create_collection(name="tools", embedding_function=_embedder)
    if not _tools_indexed:
        index_tools(tools)

    result = collection.query(
        query_texts=[normalized],
        n_results=top_k,
        include=["distances", "metadatas"]
    )
    selected_ids = result["ids"][0]
    distances = result["distances"][0]

    confident_ids = []
    for tool_id, distance in zip(selected_ids, distances):
        similarity = 1 - distance
        if similarity >= TOOL_CONFIDENCE_THRESHOLD:
            confident_ids.append(tool_id)
            logger.info(f"[TOOL_SELECT] {tool_id} | similarity={similarity:.3f} | CONFIDENT")
        else:
            logger.info(f"[TOOL_SELECT] {tool_id} | similarity={similarity:.3f} | BELOW THRESHOLD")

    if not confident_ids:
        logger.warning(f"[TOOL_SELECT] no tool met confidence threshold for: '{query}'")
        return []

    return [t for t in tools if t["function"]["name"] in confident_ids]