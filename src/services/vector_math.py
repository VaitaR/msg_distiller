"""Small pure-Python vector helpers.

Used by the SQLite repository fallback, where similarity cannot be pushed
into the database (pgvector handles it on PostgreSQL). Loads are small, so
plain Python is fast enough and avoids a numpy dependency.
"""

from math import sqrt


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity of two equal-length vectors (0.0 on zero norm)."""

    if len(a) != len(b):
        raise ValueError(f"Vector length mismatch: {len(a)} != {len(b)}")

    dot = 0.0
    norm_a = 0.0
    norm_b = 0.0
    for x, y in zip(a, b, strict=True):
        dot += x * y
        norm_a += x * x
        norm_b += y * y

    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0

    return dot / (sqrt(norm_a) * sqrt(norm_b))
