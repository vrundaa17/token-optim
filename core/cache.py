import hashlib,time,sys
from core.client import _chroma_client
from chromadb.utils import embedding_functions
from config import settings,PROJECT_ROOT
import os

CHROMA_PATH = os.path.join(PROJECT_ROOT, "storage", "chroma_db")
CACHE_TTL_SECONDS = 604800

_embedder = embedding_functions.SentenceTransformerEmbeddingFunction(model_name=settings.embedder)
_cache_collection = _chroma_client.get_or_create_collection(name="semantic_cache", embedding_function=_embedder)
 
def check_cache(query: str):
    results = _cache_collection.query(query_texts=[query], n_results=1)
    if not results["documents"][0]:
        return None, 0.0

    distance = results["distances"][0][0]
    similarity = 1-distance
    if similarity >=0.8:
        answer = results["metadatas"][0][0]["answer"]
        return answer, similarity 
    return None, similarity


def store_answer(query, answer):
    query_id = hashlib.sha256(query.strip().lower().encode()).hexdigest()
    _cache_collection.add(
        ids=[query_id],
        documents=[query],
        metadatas=[{'answer':answer}],
    )

def cleanup_cache():
    all_entries = _cache_collection.get(include=["metadatas"])
    now = time.time()
    expired_ids = [
        id_ for id_, meta in zip(all_entries["ids"], all_entries["metadatas"])
        if now - meta.get("cached_at", 0) > CACHE_TTL_SECONDS
    ]
    if expired_ids:
        _cache_collection.delete(ids=expired_ids)
        print(f"[CACHE] cleaned up {len(expired_ids)} expired entries", file=sys.stderr)
    return len(expired_ids)