"""Text -> embedding vector, via OpenAI ``text-embedding-3-small``.

An embedding turns a piece of text into a list of 1536 floats that encodes its
meaning, so texts with similar meaning produce vectors pointing in similar
directions. We store these in the ``facts.embedding`` column (see ``db.py``) and
rank stored facts by cosine distance to a query embedding — that's Tier 2 recall.

Only embeddings use OpenAI; Claude is still the brain. The client is built lazily
so importing this module (and running the Phase 0 bot) never requires the key.

Run the smoke test:  ``python -m assistant.orchestrator.embeddings``
"""
from __future__ import annotations

import math
from functools import lru_cache

from openai import OpenAI

from assistant.config import settings

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIM = 1536  # text-embedding-3-small's native size; must match db.py's vector(N)


@lru_cache(maxsize=1)
def _client() -> OpenAI:
    """Build the OpenAI client once, failing loudly if the key is missing."""
    if not settings.openai_api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set in .env — it's required for Tier 2 embeddings."
        )
    return OpenAI(api_key=settings.openai_api_key)


def embed(text: str) -> list[float]:
    """Embed a single piece of text.

    Args:
        text: The text to embed (a user message, or a fact to store).

    Returns:
        A list of ``EMBEDDING_DIM`` floats — the meaning vector for ``text``.

    Raises:
        RuntimeError: If ``OPENAI_API_KEY`` is not configured.
    """
    response = _client().embeddings.create(model=EMBEDDING_MODEL, input=text)
    return response.data[0].embedding


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity of two vectors: 1.0 = identical direction, 0 = unrelated.

    (pgvector's ``<=>`` operator returns cosine *distance* = ``1 - similarity``;
    we compute similarity here just to make the smoke test easy to read.)
    """
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    return dot / (norm_a * norm_b)


if __name__ == "__main__":
    dogs = embed("I love dogs")
    puppies = embed("Puppies are wonderful")
    market = embed("The stock market fell sharply today")

    print(f"Embedding dimension: {len(dogs)}  (first 5 numbers: {[round(x, 4) for x in dogs[:5]]})")
    print()
    print("Cosine similarity (higher = more similar in meaning):")
    print(f"  'I love dogs'  vs  'Puppies are wonderful'    -> {_cosine_similarity(dogs, puppies):.3f}")
    print(f"  'I love dogs'  vs  'The stock market fell...'  -> {_cosine_similarity(dogs, market):.3f}")
