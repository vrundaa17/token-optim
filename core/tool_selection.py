from config import settings,PROJECT_ROOT
import sys,os
from core.client import _chroma_client
from chromadb.utils import embedding_functions
import os
import logging; 
logger = logging.getLogger("token")
CHROMA_PATH = os.path.join(PROJECT_ROOT, "storage", "chroma_db")

_embedder = embedding_functions.SentenceTransformerEmbeddingFunction(model_name=settings.embedder)



ALIASES = {
    "create_entities": "save a note store information remember something write something down create a memory",
    "search_nodes": "find a note search memory look up information retrieve",
    "read_graph": "show all notes list everything stored show memory",
    "add_observations": "update a note add to existing note append information",
    "open_nodes": "open a note read a specific note get a note",
}

_tools_indexed = False

def index_tools(tools):
    global _tools_indexed
    collection = _chroma_client.get_or_create_collection(name="tools", embedding_function=_embedder)
    enriched_docs = []
    for t in tools:
        name = t['function']['name']
        desc = t['function']['description']
        alias = ALIASES.get(name, "")
        enriched_docs.append(f"{desc} {alias}".strip())
    
    collection.upsert(
        ids=[t['function']['name'] for t in tools],
        documents=enriched_docs,
        metadatas=[{"name": t['function']['name']} for t in tools],
    )
    _tools_indexed = True
    
    
def select_relevant_tools(tools: list[dict], query: str, top_k: int = 2) -> list[dict]:
    global _tools_indexed
    if len(tools) <= top_k:
        return tools

    collection = _chroma_client.get_or_create_collection(name="tools", embedding_function=_embedder)
    if not _tools_indexed:
        index_tools(tools)
        
    result = collection.query(
        query_texts=[query],
        n_results=top_k,
    )
    selected = result["ids"][0]
    return [t for t in tools if t["function"]["name"] in selected]