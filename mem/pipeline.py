from mem.extract import extract
from mem.retrieve import retrieve
from mem.graph_store import store, get_stable_facts

def get_static_context(user_id, max_facts=5):
    facts = get_stable_facts(user_id)
    return "\n".join(facts[:max_facts])

def build_prompt(user_id,message):
    static_context = get_stable_facts(user_id)
    relevant = retrieve(user_id,message)
    relevant = [f for f in relevant if f not in static_context]
    parts = []
    if static_context:
        parts.append(f"Static context : {"\n".join(static_context)}")
    if relevant:
        parts.append(f"Relevant context : {"\n".join(relevant)}")
    parts.append(f"User: {message}")
    return "\n\n".join(parts)

def remember_turn(user_id,message):
    res = extract(message)
    store(user_id, res)
    return res
