"""Tier 2 (learned facts) store — where embeddings meet Postgres.

This is the RAG layer. ``db.py`` owns the connection/schema and knows nothing
about OpenAI; ``embeddings.py`` turns text into vectors and knows nothing about
Postgres. This module is the seam that ties them together:

* ``add_fact(chat_id, content)``     -> embed the text, store the row. (write path)
* ``retrieve_top_k(chat_id, query)`` -> embed the query, return the closest facts. (read path)

"Closest" is cosine distance via pgvector's ``<=>`` operator: 0.0 = identical
meaning, ~1.0 = unrelated. ``ORDER BY embedding <=> query LIMIT k`` is the entire
retrieval step — we inject only those top-k facts into Claude's context, never the
whole store.

Smoke test:  ``python -m assistant.orchestrator.facts``
"""
from __future__ import annotations

import json

import anthropic
from pgvector import Vector  # wraps a list so psycopg sends the `vector` type, not a float array

from assistant.config import settings
from assistant.orchestrator.db import connect
from assistant.orchestrator.embeddings import embed

_client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

# Strict JSON shape Claude must return when consolidating — same idea as OpenAI
# Structured Outputs: constrain the model so we can json.loads() with confidence.
_CONSOLIDATE_SCHEMA = {
    "type": "object",
    "properties": {
        "facts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "content": {"type": "string"},
                    "kind": {"type": "string", "enum": ["fact", "preference"]},
                },
                "required": ["content", "kind"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["facts"],
    "additionalProperties": False,
}


def add_fact(chat_id: int, content: str, kind: str = "fact") -> int:
    """Embed ``content`` and store it as a fact for ``chat_id``.

    Args:
        chat_id: The owning Telegram chat (so facts are per-user).
        content: The text to remember.
        kind: A tag for the fact's type (default ``"fact"``).

    Returns:
        The new row's id.
    """
    vector = embed(content)
    with connect() as conn:
        row = conn.execute(
            "INSERT INTO facts (chat_id, content, embedding, kind) "
            "VALUES (%s, %s, %s, %s) RETURNING id",
            (chat_id, content, Vector(vector), kind),
        ).fetchone()
        conn.commit()
    return row[0]


def retrieve_top_k(chat_id: int, query: str, k: int = 3) -> list[dict]:
    """Return the ``k`` facts most relevant to ``query`` for ``chat_id``.

    Embeds the query, then ranks this user's facts by cosine distance to it.
    The ``%s::vector`` casts and ``embedding <=> %s`` operator are pgvector doing
    the nearest-neighbor search inside Postgres.

    Args:
        chat_id: The owning chat — we only search this user's facts.
        query: The text to find relevant facts for (usually the user's message).
        k: How many facts to return.

    Returns:
        A list of dicts ``{"content", "kind", "distance"}``, nearest first.
    """
    query_vector = Vector(embed(query))
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT content, kind, embedding <=> %s AS distance
            FROM facts
            WHERE chat_id = %s
            ORDER BY embedding <=> %s
            LIMIT %s
            """,
            (query_vector, chat_id, query_vector, k),
        ).fetchall()
    return [{"content": c, "kind": kind, "distance": float(d)} for c, kind, d in rows]


def consolidate(chat_id: int) -> dict:
    """Clean up a user's Tier 2 facts: merge duplicates, resolve contradictions, prune.

    The hard part of memory is consistency, not capture. We let Claude do the
    judgement (with a strict JSON schema so the output is parseable), then atomically
    replace the store with the cleaned set, re-embedding each survivor.

    Args:
        chat_id: Whose facts to consolidate.

    Returns:
        ``{"before": int, "after": int, "changed": bool}``.
    """
    with connect() as conn:
        rows = conn.execute(
            "SELECT content, kind FROM facts WHERE chat_id = %s ORDER BY id", (chat_id,)
        ).fetchall()
    if len(rows) < 2:
        return {"before": len(rows), "after": len(rows), "changed": False}

    listing = "\n".join(f"- ({kind}) {content}" for content, kind in rows)
    prompt = (
        "You maintain a long-term memory store of facts about Brian. Here is the "
        "current set:\n\n"
        f"{listing}\n\n"
        "Return a cleaned set that: merges duplicates and near-duplicates into one "
        "clear statement; resolves contradictions by keeping the most recent or most "
        "specific truth; drops trivia or anything not durably useful. Keep each item a "
        "concise standalone sentence and preserve its kind ('fact' or 'preference')."
    )
    resp = _client.messages.create(
        model=settings.model_reasoning,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
        output_config={"format": {"type": "json_schema", "schema": _CONSOLIDATE_SCHEMA}},
    )
    cleaned = json.loads("".join(b.text for b in resp.content if b.type == "text"))["facts"]

    # Atomic swap: delete the old rows and insert the cleaned set in one transaction.
    # If embedding fails mid-loop, the `with` block rolls back and nothing is lost.
    with connect() as conn:
        conn.execute("DELETE FROM facts WHERE chat_id = %s", (chat_id,))
        for item in cleaned:
            conn.execute(
                "INSERT INTO facts (chat_id, content, embedding, kind) VALUES (%s, %s, %s, %s)",
                (chat_id, item["content"], Vector(embed(item["content"])), item["kind"]),
            )
        conn.commit()

    return {"before": len(rows), "after": len(cleaned), "changed": True}


if __name__ == "__main__":
    # Use a throwaway chat id so the smoke test never touches real data.
    TEST_CHAT = -1

    # Reset, then seed a few facts that share NO words with the queries below.
    with connect() as conn:
        conn.execute("DELETE FROM facts WHERE chat_id = %s", (TEST_CHAT,))
        conn.commit()

    for fact in [
        "Brian goes to the gym every day at 6pm.",
        "Brian is relocating from Santo Domingo to Spain.",
        "Brian's favorite programming language is Python.",
        "Brian prefers tabs over spaces when writing code.",
    ]:
        add_fact(TEST_CHAT, fact)

    for query in ["When does he work out?", "Where is he moving to?"]:
        print(f"\nQuery: {query!r}")
        for hit in retrieve_top_k(TEST_CHAT, query, k=2):
            print(f"  distance={hit['distance']:.3f}  {hit['content']}")

    # Clean up the throwaway rows.
    with connect() as conn:
        conn.execute("DELETE FROM facts WHERE chat_id = %s", (TEST_CHAT,))
        conn.commit()
