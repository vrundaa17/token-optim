import tiktoken

_encoder = tiktoken.get_encoding("cl100k_base")

def count_tokens(text):
    return len(_encoder.encode(str(text)))

MAX_RESPONSE_TOKENS = 500
def trim_text_response(text: str, max_tokens: int = MAX_RESPONSE_TOKENS) -> tuple[str, int, int]:
    original_tokens = count_tokens(text)
    
    if original_tokens <= max_tokens:
        return text, original_tokens, original_tokens
    
    char_limit = max_tokens * 4
    trimmed =text[:char_limit]
    last_period = trimmed.rfind('.')
    if last_period > char_limit * 0.7:
        trimmed = trimmed[:last_period + 1]
    
    trimmed += f"\n\n[Response trimmed: {original_tokens} → {count_tokens(trimmed)} tokens]"
    
    return trimmed, original_tokens, count_tokens(trimmed)


    
    