import numpy as np
from sentence_transformers import SentenceTransformer
from mem.graph_store import get_all_facts, _cosine_sim

model = SentenceTransformer('all-MiniLM-L6-v2')

def retrieve(user_id, query, top_n=3, threshold=0.15):
    all_facts = get_all_facts(user_id)
    if not all_facts:
        print("[retrieve] No facts found for this user at all")
        return []

    query_vec = model.encode(query)
    scored = []
    for text, embedding in all_facts:
        if embedding is None:
            print(f"[retrieve] Skipping '{text}'")
            continue
        sim = _cosine_sim(query_vec, np.array(embedding))
        # print(f"[retrieve] sim={sim:.3f} | {text}")
        if sim >= threshold:
            scored.append((sim, text))

    scored.sort(reverse=True)
    return [text for _, text in scored[:top_n]]