import sqlite3
from config import settings
DB_PATH = settings.db_path

def get_connection():
    conn = sqlite3.connect(DB_PATH)
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
    return conn


def insert_audit_log(conn,run_id,stage,prompt_tokens,completion_tokens, message=""):
    total = prompt_tokens + completion_tokens
    conn.execute("INSERT INTO audit_log (run_id, stage, prompt_tokens, completion_tokens, total_tokens, message) VALUES (?,?,?,?,?,?)",
        (run_id,stage,prompt_tokens,completion_tokens,total,message)
    )
    conn.commit()
    return total


def get_summary(conn,run_id=None):
    if run_id:
        cursor = conn.execute(
            """SELECT stage, SUM(total_tokens), AVG(total_tokens), 
            COUNT(*) FROM audit_log where run_id= ? GROUP BY stage""",(run_id)
        )
    else:
        cursor = conn.execute(
            """SELECT stage, SUM(total_tokens), AVG(total_tokens), 
            COUNT(*) FROM audit_log GROUP BY stage""",(run_id)
        )
    return cursor.fetchall()