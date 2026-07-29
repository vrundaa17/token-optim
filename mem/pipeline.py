from mem.extract import extract
from mem.vectorsdb import store_fact, query_facts, get_stable_facts

def get_static_context(user_id, max_facts=5):
    return get_stable_facts(user_id, max_facts)


def build_prompt(user_id, message):
    static_context = get_static_context(user_id)
    relevant = query_facts(user_id, message)
    relevant = [f for f in relevant if f not in static_context]

    parts = []
    if static_context:
        parts.append(f"Static context:\n" + "\n".join(static_context))
    if relevant:
        parts.append(f"Relevant context:\n" + "\n".join(relevant))
    parts.append(f"User: {message}")
    return "\n\n".join(parts)


def remember_turn(user_id, message):
    try:
        res = extract(message)
    except Exception as e:
        print(f"[remember_turn] Extraction failed, skipping: {e}")
        return []

    for i, t in enumerate(res):
        fact_text = f"{t['subject']} {t['relation']} {t['object']}"
        fact_id = f"{user_id}_{hash(fact_text)}_{i}"
        stable = t.get("stability", "dynamic")
        store_fact(user_id, fact_id, fact_text, stable)
    return res