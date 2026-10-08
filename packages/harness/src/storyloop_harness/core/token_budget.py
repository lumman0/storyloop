"""Provider-independent text token budgeting."""

def estimate_tokens(text: str) -> int:
    """Conservative, provider-independent text estimate; includes UTF-8 cost."""
    return max(len(text), (len(text.encode("utf-8")) + 1) // 2)
