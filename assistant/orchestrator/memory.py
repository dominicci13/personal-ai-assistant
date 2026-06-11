"""Tier 3 — conversation memory: a rolling window of recent turns plus a running
summary of everything older.

Keeping every message forever is expensive and eventually overflows the context
window; keeping only the last N silently forgets anything older. Tier 3 splits the
difference: the most recent ``RECENT_TURNS`` messages are kept verbatim, and once
the log grows past ``SUMMARIZE_AFTER`` the overflow is folded into a short summary
(via a cheap Haiku call) and the raw messages are dropped.

On disk: ``{"summary": str, "messages": [ {role, content}, ... ]}``. Older files
that are a plain message list are migrated transparently on first read.
"""
from __future__ import annotations

import json
from pathlib import Path

import anthropic

from assistant.config import settings

RECENT_TURNS = 20      # keep this many recent messages verbatim
SUMMARIZE_AFTER = 30   # once the log exceeds this, fold the overflow into the summary

_client = anthropic.Anthropic(api_key=settings.anthropic_api_key)


class ConversationMemory:
    """Per-chat conversation memory (rolling window + running summary)."""

    def __init__(self, chat_id: int, data_dir: Path):
        self._dir = data_dir / "conversations"
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path = self._dir / f"{chat_id}.json"

    def _read(self) -> dict:
        """Load the stored state, migrating the legacy plain-list format."""
        if not self._path.exists():
            return {"summary": "", "messages": []}
        data = json.loads(self._path.read_text(encoding="utf-8"))
        if isinstance(data, list):  # legacy: a bare message list
            return {"summary": "", "messages": data}
        return data

    def _write(self, data: dict) -> None:
        self._path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def load(self) -> list[dict]:
        """Return the API-ready context: the summary (if any) as a leading note,
        followed by the recent raw turns."""
        data = self._read()
        messages: list[dict] = []
        if data["summary"]:
            messages.append({
                "role": "user",
                "content": f"[Summary of our earlier conversation]\n{data['summary']}",
            })
        messages.extend(data["messages"])
        return messages

    def record(self, user_text: str, assistant_text: str) -> None:
        """Append one completed turn, summarizing the overflow if the log is long.

        Persists only clean user/assistant text — never the intermediate tool_use /
        tool_result blocks or injected memory from the live API call.
        """
        data = self._read()
        data["messages"].append({"role": "user", "content": user_text})
        data["messages"].append({"role": "assistant", "content": assistant_text})

        if len(data["messages"]) > SUMMARIZE_AFTER:
            overflow = data["messages"][:-RECENT_TURNS]
            data["summary"] = self._summarize(data["summary"], overflow)
            data["messages"] = data["messages"][-RECENT_TURNS:]

        self._write(data)

    def _summarize(self, prior_summary: str, overflow: list[dict]) -> str:
        """Fold ``overflow`` messages into ``prior_summary`` via a cheap Haiku call."""
        convo = "\n".join(f"{m['role']}: {m['content']}" for m in overflow)
        prompt = (
            "You maintain a running summary of a conversation between an assistant "
            "and Brian.\n\n"
            f"Existing summary:\n{prior_summary or '(none yet)'}\n\n"
            f"New messages to fold in:\n{convo}\n\n"
            "Write an updated summary in a few sentences. Keep durable facts, "
            "decisions, and open threads; drop small talk. Be concise."
        )
        resp = _client.messages.create(
            model=settings.model_routing,  # Haiku — summarizing is a cheap, routine task
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(b.text for b in resp.content if b.type == "text").strip()
