"""Email tools exposed to Claude — Gmail, DRAFT-ONLY.

There is intentionally NO send tool: the bot creates drafts in Gmail; Brian reviews
and sends them himself. ``read``/``reply`` resolve the target email by a sender or
subject keyword among recent unread mail, so Claude doesn't juggle opaque message
ids across turns (the calendar lesson). API errors become friendly {"error"} dicts.
"""
from __future__ import annotations

from googleapiclient.errors import HttpError

from assistant.integrations import gmail


def _status(error: HttpError) -> int:
    return getattr(error, "status_code", None) or error.resp.status


def _resolve(query: str) -> list[dict]:
    """Recent unread emails whose sender or subject contains ``query``."""
    q = query.lower().strip()
    return [
        m for m in gmail.list_unread(max_results=25)
        if q in m["from"].lower() or q in m["subject"].lower()
    ]


def list_unread_emails(max_results: int = 10) -> dict:
    """Summarize recent unread inbox mail (sender, subject, snippet)."""
    try:
        emails = gmail.list_unread(max_results=max_results)
        return {"count": len(emails), "emails": emails}
    except HttpError as e:
        return {"error": f"Couldn't read your inbox (API {_status(e)})."}


def read_email(query: str) -> dict:
    """Read one unread email's full body, found by sender/subject keyword."""
    try:
        matches = _resolve(query)
        if not matches:
            return {"error": f"No unread email matching '{query}'. Try list_unread_emails."}
        if len(matches) > 1:
            return {"needs_disambiguation":
                    [{"from": m["from"], "subject": m["subject"]} for m in matches]}
        return gmail.get_message(matches[0]["id"])
    except HttpError as e:
        return {"error": f"Couldn't read that email (API {_status(e)})."}


def draft_email_reply(query: str, body: str) -> dict:
    """Draft a reply to an unread email (found by keyword) — saved to Drafts, not sent."""
    try:
        matches = _resolve(query)
        if not matches:
            return {"error": f"No unread email matching '{query}'. Try list_unread_emails."}
        if len(matches) > 1:
            return {"needs_disambiguation":
                    [{"from": m["from"], "subject": m["subject"]} for m in matches]}
        return gmail.create_draft_reply(matches[0]["id"], body)
    except HttpError as e:
        return {"error": f"Couldn't create the draft (API {_status(e)})."}


def draft_new_email(to: str, subject: str, body: str) -> dict:
    """Draft a fresh email — saved to Drafts, never sent."""
    try:
        return gmail.create_draft_new(to, subject, body)
    except HttpError as e:
        return {"error": f"Couldn't create the draft (API {_status(e)})."}
