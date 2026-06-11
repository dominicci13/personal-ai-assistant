"""Gmail integration: read the inbox + (step 4) create drafts.

OAuth is shared across Google integrations (see ``google_auth.py``). Gmail returns
message bodies as base64url-encoded MIME parts, so reading one means walking the
part tree to find the text/plain content — that's what ``_extract_body`` does.
"""
from __future__ import annotations

import base64
import re
from email.message import EmailMessage

from bs4 import BeautifulSoup
from googleapiclient.discovery import build

from assistant.integrations.google_auth import get_credentials

# Zero-width / soft-hyphen / joiner code points marketing emails use as invisible
# padding: soft hyphen, combining grapheme joiner, ZWSP/ZWNJ/ZWJ, word joiner, BOM.
# Built from code points so no invisible characters live in the source.
_INVISIBLE = re.compile(
    "[" + "".join(map(chr, (0xAD, 0x34F, 0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF))) + "]"
)


def get_service():
    """Return an authenticated Gmail API service client (v1)."""
    return build("gmail", "v1", credentials=get_credentials(), cache_discovery=False)


def _header(headers: list[dict], name: str) -> str:
    """Value of a header (case-insensitive), or '' if absent."""
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


def _decode(data: str) -> str:
    """Decode a base64url Gmail body part to text."""
    return base64.urlsafe_b64decode(data.encode()).decode("utf-8", errors="replace")


def _html_to_text(html: str) -> str:
    """Strip HTML to readable text (so Claude isn't fed raw markup)."""
    return BeautifulSoup(html, "html.parser").get_text(separator=" ", strip=True)


def _clean_text(text: str) -> str:
    """Drop invisible padding chars and collapse excess whitespace/blank lines."""
    text = _INVISIBLE.sub("", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n[ \t]*(\n[ \t]*)+", "\n\n", text)  # runs of blank lines -> one
    return text.strip()


def _extract_body(payload: dict) -> str:
    """Walk a message payload and return its text, preferring text/plain.

    Recurses through multipart containers; falls back to text/html (stripped to
    text) at a leaf if no plain-text part exists anywhere.
    """
    mime = payload.get("mimeType", "")
    body = payload.get("body", {})
    if mime == "text/plain" and body.get("data"):
        return _decode(body["data"])
    for part in payload.get("parts", []):
        text = _extract_body(part)
        if text:
            return text
    if mime == "text/html" and body.get("data"):
        return _html_to_text(_decode(body["data"]))
    return ""


def list_unread(max_results: int = 10) -> list[dict]:
    """Recent unread inbox messages, summary fields only (no bodies).

    Returns dicts: ``{id, thread_id, from, subject, date, snippet}``, newest first.
    """
    service = get_service()
    listing = (
        service.users().messages()
        .list(userId="me", labelIds=["INBOX", "UNREAD"], maxResults=max_results)
        .execute()
    )
    summaries = []
    for ref in listing.get("messages", []):
        msg = (
            service.users().messages()
            .get(userId="me", id=ref["id"], format="metadata",
                 metadataHeaders=["From", "Subject", "Date"])
            .execute()
        )
        headers = msg["payload"]["headers"]
        summaries.append({
            "id": msg["id"],
            "thread_id": msg["threadId"],
            "from": _header(headers, "From"),
            "subject": _header(headers, "Subject"),
            "date": _header(headers, "Date"),
            "snippet": msg.get("snippet", ""),
        })
    return summaries


def get_message(message_id: str) -> dict:
    """Full details of one message, including the decoded, cleaned plain-text body."""
    service = get_service()
    msg = service.users().messages().get(userId="me", id=message_id, format="full").execute()
    headers = msg["payload"]["headers"]
    return {
        "id": msg["id"],
        "thread_id": msg["threadId"],
        "from": _header(headers, "From"),
        "to": _header(headers, "To"),
        "subject": _header(headers, "Subject"),
        "date": _header(headers, "Date"),
        "body": _clean_text(_extract_body(msg["payload"])),
    }


def _raw(to: str, subject: str, body: str,
         in_reply_to: str | None = None, references: str | None = None) -> str:
    """Build a base64url-encoded RFC-2822 message. 'From' is filled by Gmail."""
    msg = EmailMessage()
    msg["To"] = to
    msg["Subject"] = subject
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = references or in_reply_to
    msg.set_content(body)
    return base64.urlsafe_b64encode(msg.as_bytes()).decode()


def create_draft_new(to: str, subject: str, body: str) -> dict:
    """Create a fresh draft email (saved to Drafts, never sent)."""
    draft = (
        get_service().users().drafts()
        .create(userId="me", body={"message": {"raw": _raw(to, subject, body)}})
        .execute()
    )
    return {"draft_id": draft["id"], "to": to, "subject": subject}


def create_draft_reply(message_id: str, body: str) -> dict:
    """Create a draft reply to ``message_id``, threaded correctly (saved to Drafts).

    Looks up the original's sender, subject, and Message-ID so the draft replies to
    the right person, carries a ``Re:`` subject, and threads (In-Reply-To/References
    + the same threadId).
    """
    service = get_service()
    orig = (
        service.users().messages()
        .get(userId="me", id=message_id, format="metadata",
             metadataHeaders=["From", "Subject", "Message-ID", "References"])
        .execute()
    )
    headers = orig["payload"]["headers"]
    to = _header(headers, "From")
    subject = _header(headers, "Subject")
    if not subject.lower().startswith("re:"):
        subject = "Re: " + subject
    original_id = _header(headers, "Message-ID")
    prior_refs = _header(headers, "References")
    references = f"{prior_refs} {original_id}".strip() if prior_refs else original_id

    raw = _raw(to, subject, body, in_reply_to=original_id, references=references)
    draft = (
        service.users().drafts()
        .create(userId="me", body={"message": {"raw": raw, "threadId": orig["threadId"]}})
        .execute()
    )
    return {"draft_id": draft["id"], "to": to, "subject": subject}
