from core.tool import select_relevant_tools
from core.cache import check_cache, store_answer
from adapters.groq_client import call_llm
from core.db import insert_audit_log,get_connection
import uuid
import pytest

run_id= str(uuid.uuid4())
TOOLS = [
    {"type": "function", "function": {"name": "calculator", "description": "Perform mathematical calculations", "parameters": {"type": "object", "properties": {"expression": {"type": "string"}}, "required": ["expression"]}}},
    {"type": "function", "function": {"name": "translator", "description": "Translate text between languages", "parameters": {"type": "object", "properties": {"text": {"type": "string"}, "target_lang": {"type": "string"}}, "required": ["text", "target_lang"]}}},
    {"type": "function", "function": {"name": "calendar", "description": "Check or schedule calendar events", "parameters": {"type": "object", "properties": {"event": {"type": "string"}, "time": {"type": "string"}}, "required": ["event", "time"]}}},
    {"type": "function", "function": {"name": "unit_converter", "description": "Convert between units of measurement", "parameters": {"type": "object", "properties": {"value": {"type": "number"}, "from_unit": {"type": "string"}, "to_unit": {"type": "string"}}, "required": ["value", "from_unit", "to_unit"]}}},
    {"type": "function", "function": {"name": "note_taker", "description": "Save a short note or reminder text", "parameters": {"type": "object", "properties": {"note": {"type": "string"}}, "required": ["note"]}}},
]

def run(user_message,conn):
    cached_answer,score= check_cache(user_message)
    if cached_answer:
        insert_audit_log(conn, run_id, "cache_hit", 0, 0, f"{user_message} (sim={score})")
        print(f"[CACHE HIT] {user_message}")
        return cached_answer
    relevant_tools = select_relevant_tools(TOOLS, user_message, top_k=2)
    messages = [{"role": "user", "content": user_message}]

    response = call_llm(messages=messages, tools=relevant_tools)
    if response is None:
        return None
    
    msg = response.choices[0].message
    if msg.tool_calls:
        messages.append({"role": "assistant", "tool_calls": msg.tool_calls})
        for tool_call in msg.tool_calls:
            messages.append({"role":"tool","tool_call_id":tool_call.id,"content":"mock result: 540"})
        response = call_llm(messages=messages, tools=relevant_tools)
        msg = response.choices[0].message
        
    usage = response.usage
    insert_audit_log(conn,run_id,"success",usage.prompt_tokens, usage.completion_tokens,user_message)
    answer = msg.content or ""
    if answer:
        store_answer(user_message, answer)
    return answer

    
@pytest.mark.parametrize(
    "message",
    [
        "What's 45 times 12?",
        "Translate 'good morning' to Spanish",
        "Can you multiply 45 by 12 for me?",
        "Schedule a meeting for tomorrow at 3pm",
        "How do you say 'good morning' in Spanish?",
    ],
)

def test_run(message):
    conn = get_connection()
    result = run(message, conn)
    assert result is not None, f"Failed for message: {message}"
    conn.close()