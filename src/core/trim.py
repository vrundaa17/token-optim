import tiktoken

_encoder = tiktoken.get_encoding("cl100k_base")

def count_tokens(text):
    return len(_encoder.encode(str(text)))

MAX_RESPONSE_TOKENS = 500
import json

def _is_json(text: str) -> bool:
    stripped = text.strip()
    return stripped.startswith(("{", "["))

def trim_text_response(text: str, max_tokens: int = MAX_RESPONSE_TOKENS) -> tuple[str, int, int]:
    original_tokens = count_tokens(text)
    
    if original_tokens <= max_tokens:
        return text, original_tokens, original_tokens
    
    # JSON response — don't cut, just warn
    if _is_json(text):
        note = f"\n\n[JSON response: {original_tokens} tokens — not trimmed to preserve structure]"
        result = text + note
        return result, original_tokens, original_tokens
    
    # plain text — cut at sentence boundary
    char_limit = max_tokens * 4
    trimmed = text[:char_limit]
    last_period = trimmed.rfind('.')
    if last_period > char_limit * 0.7:
        trimmed = trimmed[:last_period + 1]
    
    trimmed += f"\n\n[Response trimmed: {original_tokens} → {count_tokens(trimmed)} tokens]"
    return trimmed, original_tokens, count_tokens(trimmed)