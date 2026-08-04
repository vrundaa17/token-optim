from groq import Groq
from config import settings

_client = Groq(api_key=settings.groq_api_key)

def call_llm(messages,tools):
    try:
        response = _client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages = messages,
            tools=tools,
            temperature=0,
        ) 
        return response
    except Exception as e:
        print(f"[GROQ] failed {e}")
        return None