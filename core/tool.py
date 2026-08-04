from config import settings,PROJECT_ROOT
import chromadb,sys,os
from chromadb.utils import embedding_functions
import os
CHROMA_PATH = os.path.join(PROJECT_ROOT, "storage", "chroma_db")

_embedder = embedding_functions.SentenceTransformerEmbeddingFunction(model_name=settings.embedder)
_client = chromadb.PersistentClient(path=CHROMA_PATH)
_tool_collection = _client.get_or_create_collection(name="tools",embedding_function=_embedder)


def index_tools(tools):
    _tool_collection.upsert(
        ids=[t['function']['name'] for t in tools],
        documents=[t["function"]["description"] for t in tools],
        metadatas=[{"name": t["function"]["name"]} for t in tools],
    )
    

def select_relevant_tools(tools: list[dict], query: str, top_k: int = 2) -> list[dict]:
# def select_relevant_tools(tools, query, top_k=2):

    if len(tools) <= top_k:
        return tools

    index_tools(tools)
    print("Count:", _tool_collection.count(), file=sys.stderr)
    result = _tool_collection.query(
        query_texts=[query],
        n_results=top_k,
    )
    print(result, file=sys.stderr)
    selected = result["ids"][0]
    return [t for t in tools if t["function"]["name"] in selected]