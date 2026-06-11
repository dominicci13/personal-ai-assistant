"""Tier 1 identity — the small, always-in-context block about Brian.

Two parts, both folded into the system prompt every turn:

* ``data/IDENTITY.md`` — hand-written, stable: who Brian is, how he works. Personal,
  so it's gitignored; ``data/IDENTITY.example.md`` ships as a template.
* ``data/profile.md`` — a short, curated list of learned preferences. The
  ``remember(kind="preference")`` tool appends here, so durable preferences live in
  the always-present identity block instead of being retrieved from Tier 2.

Keep this tier SMALL: it's sent on every message (and gets prompt-cached in step 9),
so it's the one tier you pay for on every turn.
"""
from __future__ import annotations

from pathlib import Path

from assistant.config import settings
from assistant.orchestrator.persona import SYSTEM_PROMPT

_IDENTITY_PATH = settings.data_dir / "IDENTITY.md"
_PROFILE_PATH = settings.data_dir / "profile.md"


def _read(path: Path) -> str:
    """Return a file's stripped text, or '' if it doesn't exist yet."""
    return path.read_text(encoding="utf-8").strip() if path.exists() else ""


def load_identity() -> str:
    """The hand-written identity block (``data/IDENTITY.md``)."""
    return _read(_IDENTITY_PATH)


def load_profile() -> str:
    """The curated learned-preferences block (``data/profile.md``)."""
    return _read(_PROFILE_PATH)


def add_preference(content: str) -> None:
    """Append a durable preference to the curated Tier 1 profile.

    Step 12 adds a consolidation pass (dedupe / merge / resolve contradictions);
    for now we simply append a bullet.

    Args:
        content: The preference to record, as a standalone sentence.
    """
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    with _PROFILE_PATH.open("a", encoding="utf-8") as f:
        f.write(f"- {content.strip()}\n")


def build_system_prompt() -> str:
    """Assemble the full system block: behavior + identity + learned preferences.

    Called once per turn in the agent loop. Sections with no content are omitted,
    so an empty profile adds nothing.

    Returns:
        The complete system prompt string passed to Claude.
    """
    parts = [SYSTEM_PROMPT]
    if identity := load_identity():
        parts.append("# What you know about Brian\n" + identity)
    if profile := load_profile():
        parts.append("# Learned preferences (curated)\n" + profile)
    return "\n\n".join(parts)
