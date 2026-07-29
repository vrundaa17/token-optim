import os
CHROMA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "chroma_db")
CHROMA_PATH = os.path.abspath(CHROMA_PATH)

import chromadb
from sentence_transformers import SentenceTransformer
client = chromadb.PersistentClient(path=CHROMA_PATH)
collection = client.get_or_create_collection("facts")

model = SentenceTransformer('all-MiniLM-L6-v2')

def get_stable_facts(user_id, max_facts=5):
    results = collection.get(
        where={"$and": [{"user_id": user_id}, {"stability": "stable"}]},
        limit=max_facts
    )
    return results.get("documents", []) or []

def store_fact(user_id, fact_id, fact_text, stability="dynamic" ):
    embedding = model.encode(fact_text).tolist()
    collection.add(
        ids=[fact_id],embeddings=[embedding],
        documents=[fact_text],metadatas=[{"user_id": user_id, "stability": stability}]
    )
    
def query_facts(user_id, query_text, top_n=5, stability_filter=None, relative_gap=0.3):
    query_embedding = model.encode(query_text).tolist()
    where_clause = {"user_id": user_id}
    if stability_filter:
        where_clause = {"$and": [{"user_id": user_id}, {"stability": stability_filter}]}

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_n,
        where=where_clause,
        include=["documents", "distances"]
    )
    if not results["documents"] or not results["documents"][0]:
        return []
    docs = results["documents"][0]
    distances = results["distances"][0]
    if not distances:
        return []
    
    best_distance = distances[0]
    filtered = [doc for doc, dist in zip(docs, distances) if dist <= best_distance + relative_gap]
    return filtered

if __name__ =="__main__":
    store_fact("test_user", "fact_1", "Project uses FastAPI", stability="stable")
    store_fact("test_user", "fact_2", "Project uses SQLite", stability="stable")
    store_fact("test_user", "fact_3", "Dogs only barks", stability="stable")
    store_fact("test_user", "fact_4", "This the 7 wonder of the world", stability="stable")
    store_fact("test_user", "fact_5", "The new model proves to be the best ", stability="stable")
    
    results = query_facts("test_user", "what are the wonders?")
    print(results)