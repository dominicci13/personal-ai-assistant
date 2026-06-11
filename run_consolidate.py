"""Consolidate the configured user's Tier 2 memory (merge dupes, resolve
contradictions, prune). Run on demand, or on a schedule later.

Usage:  python run_consolidate.py
"""
from assistant.config import settings
from assistant.orchestrator.facts import consolidate


def main() -> None:
    result = consolidate(settings.allowed_telegram_user_id)
    if result["changed"]:
        print(f"Consolidated Tier 2 facts: {result['before']} -> {result['after']}.")
    else:
        print(f"Nothing to consolidate ({result['before']} fact(s)).")


if __name__ == "__main__":
    main()
