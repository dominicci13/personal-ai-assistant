"""Postgres + pgvector access layer for Tier 2 (learned-facts) memory.

One module owns the connection and schema so the rest of the app never writes
raw connection code. Two entry points:

* ``init_db()`` — create the extension, table, and indexes (idempotent; safe to
  re-run). Run once after the database is up: ``python -m assistant.orchestrator.db``.
* ``connect()`` — open a connection that knows the pgvector type, so you can pass
  a plain Python list where the query expects a ``vector`` (used in steps 4-5).

The ``facts`` table holds one row per remembered fact: the text, its 1536-dim
embedding (OpenAI ``text-embedding-3-small``), the owning chat, and a kind tag.
Retrieval ranks rows by cosine distance to a query embedding (``<=>``).
"""
from __future__ import annotations

import psycopg
from pgvector.psycopg import register_vector

from assistant.config import settings

EMBEDDING_DIM = 1536  # OpenAI text-embedding-3-small. Must match the model used to embed.

# Schema is split into single statements so we can run them one-by-one.
# `IF NOT EXISTS` everywhere keeps init_db() idempotent.
_SCHEMA_STATEMENTS = (
    "CREATE EXTENSION IF NOT EXISTS vector",
    f"""
    CREATE TABLE IF NOT EXISTS facts (
        id          BIGSERIAL PRIMARY KEY,
        chat_id     BIGINT       NOT NULL,
        content     TEXT         NOT NULL,
        embedding   vector({EMBEDDING_DIM}) NOT NULL,
        kind        TEXT         NOT NULL DEFAULT 'fact',
        created_at  TIMESTAMPTZ  NOT NULL DEFAULT now()
    )
    """,
    # HNSW index on cosine distance = fast approximate nearest-neighbor search.
    # vector_cosine_ops tells the index we'll query with the <=> (cosine) operator.
    "CREATE INDEX IF NOT EXISTS facts_embedding_idx "
    "ON facts USING hnsw (embedding vector_cosine_ops)",
    # Plain b-tree index so per-user filtering (WHERE chat_id = ...) stays fast.
    "CREATE INDEX IF NOT EXISTS facts_chat_id_idx ON facts (chat_id)",
)


def init_db() -> None:
    """Create the pgvector extension, the ``facts`` table, and its indexes.

    Idempotent — every statement uses ``IF NOT EXISTS``, so re-running it is a
    no-op. Does not register the vector type adapter, because the extension may
    not exist yet on the very first run.

    Raises:
        psycopg.OperationalError: If the database is unreachable (is Docker up?).
    """
    with psycopg.connect(settings.database_url) as conn:
        for statement in _SCHEMA_STATEMENTS:
            conn.execute(statement)
        conn.commit()


def connect() -> psycopg.Connection:
    """Open a connection with the pgvector type registered.

    Registration teaches psycopg to translate between Python lists and the
    Postgres ``vector`` type, so later code can pass ``[0.1, 0.2, ...]`` straight
    into a query. The caller owns the connection and should close it (or use it
    as a context manager).

    Returns:
        An open ``psycopg.Connection`` ready for vector reads/writes.
    """
    conn = psycopg.connect(settings.database_url)
    register_vector(conn)  # needs the extension to already exist (init_db ran)
    return conn


if __name__ == "__main__":
    init_db()
    print(f"Schema ready: 'facts' table with vector({EMBEDDING_DIM}) embeddings + HNSW index.")
