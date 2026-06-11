"""The `remember()` write path — the assistant's continuous-learning tool.

When the user says "remember…", "from now on…", or states a durable fact about
themselves, Claude calls this. It stores the item in Tier 2 (pgvector) so a later,
unrelated conversation can retrieve it.

Step 6 routes BOTH kinds to Tier 2 (tagged via the `kind` column). Step 7 will
redirect kind="preference" to the small Tier 1 curated profile instead, so durable
preferences live in the always-present identity block rather than being retrieved.
"""
from __future__ import annotations

from assistant.orchestrator.facts import add_fact
from assistant.orchestrator.identity import add_preference


def remember(chat_id: int, content: str, kind: str = "fact") -> dict:
    """Store something about the user in long-term memory.

    Routes by ``kind``: a ``"preference"`` goes to the Tier 1 curated profile
    (always in context); a ``"fact"`` goes to Tier 2 (pgvector, retrieved on demand).

    Args:
        chat_id: The owning Telegram chat (Tier 2 facts are per-user).
        content: The fact or preference to remember, as a standalone sentence.
        kind: ``"fact"`` or ``"preference"``.

    Returns:
        A small JSON-able dict confirming the write (becomes the tool_result).
    """
    if kind == "preference":
        add_preference(content)
        return {"remembered": True, "kind": "preference", "tier": 1}
    fact_id = add_fact(chat_id, content, kind="fact")
    return {"remembered": True, "id": fact_id, "kind": "fact", "tier": 2}
