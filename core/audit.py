import tiktoken

_encoder = tiktoken.get_encoding("cl100k_base")

def count_tokens(text):
    return len(_encoder.encode(str(text)))

def token_reduction_pct(before, after) :
    if before == 0:
        return 0.0
    return round((before - after) / before * 100, 1)

