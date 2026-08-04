from groq import Groq
import sqlite3
import uuid
from sentence_transformers import SentenceTransformer
import numpy as np
import os
from dotenv import load_dotenv
load_dotenv()


import tiktoken
import requests


encoder = tiktoken.get_encoding("cl100k_base")
conn = sqlite3.connect("storage/token_audit.db")


conn.execute("""
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
    run_id TEXT,
    stage TEXT,
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    total_tokens INTEGER,
    message TEXT
)
""")
conn.commit()
RUN_ID = str(uuid.uuid4())[:8]

def log_audit(stage, prompt_tokens, completion_tokens, message=""):
    total = prompt_tokens + completion_tokens
    conn.execute(
        "INSERT INTO audit_log (run_id, stage, prompt_tokens, completion_tokens, total_tokens, message) VALUES (?, ?, ?, ?, ?, ?)",
        (RUN_ID, stage, prompt_tokens, completion_tokens, total, message)
    )
    conn.commit()
    print(f"[{stage}] prompt={prompt_tokens} completion={completion_tokens} total={total}")

client = Groq(api_key=os.getenv("GROQ_API_KEY"))


embedder = SentenceTransformer('all-MiniLM-L6-v2')
tool_descriptions = [t["function"]["description"] for t in TOOLS]
tool_embeddings = embedder.encode(tool_descriptions)

def select_relevant_tools(user_message, top_k=2):
    query_embedding = embedder.encode([user_message])[0]
    sims = np.dot(tool_embeddings, query_embedding) / (
        np.linalg.norm(tool_embeddings, axis=1) * np.linalg.norm(query_embedding)
    )
    top_indices = np.argsort(sims)[-top_k:][::-1]
    return [TOOLS[i] for i in top_indices]


def chat_baseline(user_message, history, retries=1):
    history.append({"role": "user", "content": user_message})
    for attempt in range(retries + 1):
        try:
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile", messages=history, tools=TOOLS, temperature=0,
            )
            usage = response.usage
            log_audit("baseline", usage.prompt_tokens, usage.completion_tokens, user_message)
            history.append({"role": "assistant", "content": response.choices[0].message.content or ""})
            return response
        except Exception as e:
            if attempt < retries:
                continue
            print(f"[BASELINE] failed: {e}")
            log_audit("baseline_failed", 0, 0, user_message)
            return None


def chat_optimised(user_message, history, retries=1):
    history.append({"role": "user", "content": user_message})
    relevant_tools = select_relevant_tools(user_message)
    for attempt in range(retries + 1):
        try:
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile", messages=history, tools=relevant_tools, temperature=0,
            )
            usage = response.usage
            log_audit("optimised_tool_selection", usage.prompt_tokens, usage.completion_tokens,
                       f"{user_message} (tools: {[t['function']['name'] for t in relevant_tools]})")
            history.append({"role": "assistant", "content": response.choices[0].message.content or ""})
            return response
        except Exception as e:
            if attempt < retries:
                continue
            print(f"[OPTIMISED] failed: {e}")
            log_audit("optimised_failed", 0, 0, user_message)
            return None



CITY_COORDS = { 
    "mumbai": (19.076, 72.877),
    "delhi": (28.613, 77.209),
    "bhavnagar": (21.766, 72.152),
    "bangalore": (12.972, 77.594),
}

def call_weather_api_raw(city):
    lat, lon = CITY_COORDS.get(city.lower(), (19.076, 72.877)) 
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,relative_humidity_2m,wind_speed_10m,weather_code,pressure_msl,cloud_cover,precipitation&hourly=temperature_2m,precipitation_probability&daily=temperature_2m_max,temperature_2m_min&timezone=auto"
    response = requests.get(url)
    return response.json()  

def call_weather_api_trimmed(city):
    raw = call_weather_api_raw(city)
    current = raw["current"]
    return {
        "city": city,
        "temperature_c": current["temperature_2m"],
        "humidity_pct": current["relative_humidity_2m"],
        "wind_kmh": current["wind_speed_10m"],
    }
    
import json

def audit_response_trimming(city):
    raw = call_weather_api_raw(city)
    trimmed = call_weather_api_trimmed(city)
    
    raw_tokens = len(encoder.encode(json.dumps(raw)))
    trimmed_tokens = len(encoder.encode(json.dumps(trimmed)))

    log_audit("response_raw", raw_tokens, 0, f"weather:{city}")
    log_audit("response_trimmed", trimmed_tokens, 0, f"weather:{city}")

    saved = raw_tokens - trimmed_tokens
    print(f"[{city}] raw={raw_tokens} tokens, trimmed={trimmed_tokens} tokens, saved={saved} ({saved/raw_tokens*100:.1f}%)")
import numpy as np


conn.execute("""
CREATE TABLE IF NOT EXISTS semantic_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question TEXT,
    answer TEXT,
    embedding BLOB
)
""")
conn.commit()

CACHE_SIMILARITY_THRESHOLD = 0.90 

def embedding_to_blob(embedding):
    return embedding.astype(np.float32).tobytes()

def blob_to_embedding(blob):
    return np.frombuffer(blob, dtype=np.float32)

def check_cache(user_message):
    query_embedding = embedder.encode([user_message])[0]
    rows = conn.execute("SELECT id, question, answer, embedding FROM semantic_cache").fetchall()

    best_match = None
    best_score = -1
    for row_id, question, answer, emb_blob in rows:
        cached_embedding = blob_to_embedding(emb_blob)
        sim = np.dot(query_embedding, cached_embedding) / (
            np.linalg.norm(query_embedding) * np.linalg.norm(cached_embedding)
        )
        if sim > best_score:
            best_score = sim
            best_match = (question, answer)

    if best_match and best_score >= CACHE_SIMILARITY_THRESHOLD:
        return best_match[1], best_score
    return None, best_score

def store_in_cache(user_message, answer):
    embedding = embedder.encode([user_message])[0]
    conn.execute(
        "INSERT INTO semantic_cache (question, answer, embedding) VALUES (?, ?, ?)",
        (user_message, answer, embedding_to_blob(embedding))
    )
    conn.commit()

# ─────────────────────────────
# STAGE 4: CHAT WITH CACHE CHECK FIRST
# ─────────────────────────────
def chat_with_cache(user_message, history, retries=1):
    cached_answer, score = check_cache(user_message)
    if cached_answer:
        # cache hit — zero LLM tokens spent
        log_audit("cache_hit", 0, 0, f"{user_message} (similarity={score:.3f})")
        print(f"[CACHE HIT] '{user_message}' matched with similarity {score:.3f} → returning cached answer, 0 tokens used")
        return cached_answer

    # cache miss — proceed to actual LLM call (using your Stage 2 optimized path)
    history.append({"role": "user", "content": user_message})
    relevant_tools = select_relevant_tools(user_message)
    for attempt in range(retries + 1):
        try:
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile", messages=history, tools=relevant_tools, temperature=0,
            )
            usage = response.usage
            log_audit("cache_miss_llm_call", usage.prompt_tokens, usage.completion_tokens, user_message)
            answer = response.choices[0].message.content or ""
            store_in_cache(user_message, answer)
            return answer
        except Exception as e:
            if attempt < retries:
                continue
            print(f"[CACHE_MISS] failed: {e}")
            log_audit("cache_miss_failed", 0, 0, user_message)
            return None
if __name__ == "__main__":
    test_pairs = [
        "What's 245 times 17?",
        "Can you calculate 245 multiplied by 17?", 
        "What's the weather in Mumbai?",
        "Tell me the weather in Mumbai right now",
    ]
    for msg in test_pairs:
        chat_with_cache(msg, [])