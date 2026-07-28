import os
from neo4j import GraphDatabase,basic_auth
from sentence_transformers import SentenceTransformer
import numpy as np
from dotenv import load_dotenv
load_dotenv()


driver = GraphDatabase.driver(
    uri=os.getenv("NEO4J_URI"),
    auth=basic_auth (os.getenv("NEO4J_USERNAME"), os.getenv("NEO4J_PASSWORD"))
    )

driver.verify_connectivity()

model = SentenceTransformer('all-MiniLM-L6-v2')

def _cosine_sim(a, b):
    a, b = np.array(a), np.array(b)
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))


def _get_facts_for_user(tx, user_id):
    result = tx.run(
        """
            MATCH (s:Entity {user_id: $user_id})-[r:RELATION]->(o:Entity {user_id: $user_id})
            RETURN s.name AS subject, r.type AS relation, o.name AS object, s.embedding AS sub_embed
        """, user_id=user_id)
    return [
        (f"{rec['subject']} {rec['relation']} {rec['object']}", rec['sub_embed'])
        for rec in result]
    
def _get_facts_by_stability(tx, user_id, stability):
    result = tx.run("""
        MATCH (s:Entity {user_id: $user_id})-[r:RELATION {stability: $stability}]->(o:Entity {user_id: $user_id})
        RETURN s.name AS subject, r.type AS relation, o.name AS object
    """, user_id=user_id, stability=stability)
    return [f"{rec['subject']} {rec['relation']} {rec['object']}" for rec in result]


def get_stable_facts(user_id):
    with driver.session() as session:
        return session.execute_read(_get_facts_by_stability, user_id, "stable")
    
    
def _store(tx, user_id, subject, relation, obj, sub_embed, obj_embed, stability):
    tx.run("""
        MERGE (s:Entity {user_id: $user_id, name: $subject})
        SET s.embedding = $sub_embed
        MERGE (o:Entity {user_id: $user_id, name: $object})
        SET o.embedding = $obj_embed
        MERGE (s)-[r:RELATION {type: $relation}]->(o)
        SET r.stability = $stability
    """, subject=subject, object=obj, relation=relation,
         sub_embed=sub_embed, obj_embed=obj_embed, user_id=user_id, stability=stability)
    
    
def store(user_id, triples, dup_thresh=0.9):
    
    with driver.session() as session:
        existing = session.execute_read(_get_facts_for_user, user_id)
        existing_embed = [e for _, e in existing if e is not None]

        for t in triples:
            fact_text = f"{t['subject']} {t['relation']} {t['object']}"
            fact_embed = model.encode(fact_text).tolist() 

            is_duplicate = any(_cosine_sim(fact_embed, existing_emb) >= dup_thresh for existing_emb in existing_embed)
            if is_duplicate:
                print(f"[already there] skip {fact_text}")
                continue
            stable = t.get("stability", "dynamic") 
            session.execute_write(_store, user_id, t["subject"], t["relation"], t["object"], fact_embed, fact_embed,stable)
            existing_embed.append(fact_embed)
    
def get_all_facts(user_id):
    with driver.session() as session:
        return session.execute_read(_get_facts_for_user,user_id)