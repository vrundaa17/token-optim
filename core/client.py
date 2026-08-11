# from groq import Groq
from config import settings,PROJECT_ROOT
import chromadb
import os,sys

# _groq_client = Groq(api_key=settings.groq_api_key)

# def call_llm(messages,tools):
#     try:
#         response = _groq_client.chat.completions.create(
#             model="llama-3.3-70b-versatile",
#             messages = messages,
#             tools=tools,
#             temperature=0,
#         ) 
#         return response
#     except Exception as e:
#         print(f"[GROQ] failed {e}")
#         return None


CHROMA_PATH = os.path.join(PROJECT_ROOT, "storage", "chroma_db")
_chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)