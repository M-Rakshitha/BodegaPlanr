from __future__ import annotations

import os
from functools import lru_cache

from google import genai

_EMBED_MODEL = "gemini-embedding-001"  # 3072-dim, available on this API key


@lru_cache(maxsize=1)
def _client() -> genai.Client:
    return genai.Client(api_key=os.environ["GOOGLE_API_KEY"])


def embed(text: str) -> list[float]:
    """Return a 768-dim embedding vector for text using Google text-embedding-004."""
    result = _client().models.embed_content(
        model=_EMBED_MODEL,
        contents=text,
    )
    return list(result.embeddings[0].values)
