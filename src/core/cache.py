import hashlib,time,sys
from core.client import _chroma_client
from chromadb.utils import embedding_functions
from config import settings,PROJECT_ROOT
import os
import logging
logger = logging.getLogger("token")
CHROMA_PATH = os.path.join(PROJECT_ROOT, "storage", "chroma_db")
TTL_BY_TOOL = {
    "find_tool": 300,        # 5 minutes — filesystem changes
    "ask_document": 86400,   # 1 day — PDFs don't change
    "search_all_documents": 86400,
    "list_indexed_documents": 60,  # 1 minute
}
TTL_DEFAULT = 3600 

_embedder = embedding_functions.SentenceTransformerEmbeddingFunction(model_name=settings.embedder)
_cache_collection = _chroma_client.get_or_create_collection(name="semantic_cache", embedding_function=_embedder)
 
def check_cache(query: str, tool_name: str = ""):
    results = _cache_collection.query(query_texts=[query], n_results=1)
    if not results["documents"][0]:
        return None, 0.0

    distance = results["distances"][0][0]
    similarity = 1 - distance
    if similarity >= 0.8:
        meta = results["metadatas"][0][0]
        cached_at = meta.get("cached_at", 0)
        ttl = TTL_BY_TOOL.get(tool_name, TTL_DEFAULT)
        if time.time() - cached_at > ttl:
            return None, similarity
        answer = meta['answer']
        return answer, similarity
    return None, similarity


def store_answer(query, answer):
    query_id = hashlib.sha256(query.strip().lower().encode()).hexdigest()
    try:
        _cache_collection.upsert(
            ids=[query_id],
            documents=[query],
            metadatas=[{'answer': answer, 'cached_at': time.time()}],
        )
    except Exception as e:
        logger.warning(f"[CACHE] stored failed for query : {query}  - {e}")
        

def cleanup_cache():
    all_entries = _cache_collection.get(include=["metadatas"])
    now = time.time()
    expired_ids = [
        id_ for id_, meta in zip(all_entries["ids"], all_entries["metadatas"])
        if now - meta.get("cached_at", 0) > TTL_DEFAULT
    ]
    if expired_ids:
        _cache_collection.delete(ids=expired_ids)
        print(f"[CACHE] cleaned up {len(expired_ids)} expired entries", file=sys.stderr)
    return len(expired_ids)