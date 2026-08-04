import uuid
import chromadb
from chromadb.utils import embedding_functions
from config import settings,PROJECT_ROOT
import os

CHROMA_PATH = os.path.join(PROJECT_ROOT, "storage", "chroma_db")

_embedder = embedding_functions.SentenceTransformerEmbeddingFunction(model_name=settings.embedder)
_client = chromadb.PersistentClient(path=CHROMA_PATH)
_cache_collection = _client.get_or_create_collection(name="semantic_cache", embedding_function=_embedder)

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
    _cache_collection.add(
        ids=[str(uuid.uuid4())],documents=[query],metadatas=[{'answer':answer}],
    )