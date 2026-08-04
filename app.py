from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from utils import count_tokens
from mem.pipeline import build_prompt, remember_turn


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://claude.ai"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/count")
def count(text: str):
    return {"tokens": count_tokens(text)}

@app.get("/build_prompt")
def get_build_prompt(user_id: str, message: str):
    return {"prompt": build_prompt(user_id, message)}

@app.post("/remember")
def post_remember(user_id: str, message: str):
    result = remember_turn(user_id, message)
    return {"stored": result}