"""Calendar tools exposed to Claude.

Write operations (delete / reschedule) resolve the target event by a title keyword
within a time window, so Claude never has to juggle opaque event ids across turns —
a frequent source of failed first attempts, since tool results aren't persisted.
Each wrapper also turns Google API errors into a friendly ``{"error": ...}`` dict
instead of letting an exception crash the turn.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from googleapiclient.errors import HttpError

from assistant.config import settings
from assistant.integrations.google_calendar import (
    create_event,
    delete_event,
    list_events,
    update_event,
)


def _status(error: HttpError) -> int:
    """HTTP status from an HttpError, across library versions."""
    return getattr(error, "status_code", None) or error.resp.status


def _default_window() -> tuple[str, str]:
    """Now -> +90 days in Brian's timezone — the search window when none is given."""
    now = datetime.now(ZoneInfo(settings.calendar_timezone))
    return now.isoformat(), (now + timedelta(days=90)).isoformat()


def _find_matches(title_query: str, time_min: str | None, time_max: str | None) -> list[dict]:
    """Events whose title contains ``title_query`` (case-insensitive) in the window."""
    if not time_min or not time_max:
        time_min, time_max = _default_window()
    q = title_query.lower().strip()
    return [
        e for e in list_events(time_min, time_max, max_results=50)
        if q in (e.get("summary") or "").lower()
    ]


def _resolve_one(title_query: str, time_min: str | None, time_max: str | None):
    """Return (event, None) on exactly one match, else (None, response-to-return)."""
    matches = _find_matches(title_query, time_min, time_max)
    if not matches:
        return None, {"error": f"No event matching '{title_query}' found. "
                               "Check the title or widen the date range."}
    if len(matches) > 1:
        return None, {"needs_disambiguation": [
            {"summary": m["summary"], "start": m["start"]} for m in matches]}
    return matches[0], None


def list_calendar_events(time_min: str, time_max: str) -> dict:
    """Return Brian's events in ``[time_min, time_max]`` for the agent to read."""
    try:
        events = list_events(time_min, time_max)
        return {"count": len(events), "events": events}
    except HttpError as e:
        return {"error": f"Couldn't read the calendar (API {_status(e)})."}


def create_calendar_event(summary: str, start: str, end: str,
                          description: str | None = None) -> dict:
    """Create an event. Confirm-first is enforced by the tool description."""
    try:
        return create_event(summary, start, end, description=description)
    except HttpError as e:
        return {"error": f"Couldn't create the event (API {_status(e)})."}


def delete_calendar_event(title_query: str, time_min: str | None = None,
                          time_max: str | None = None) -> dict:
    """Find an event by title keyword and delete it (no id juggling for Claude)."""
    try:
        event, response = _resolve_one(title_query, time_min, time_max)
        if response is not None:
            return response
        delete_event(event["id"])
        return {"deleted": True, "summary": event["summary"], "start": event["start"]}
    except HttpError as e:
        return {"error": f"Couldn't delete the event (API {_status(e)})."}


def update_calendar_event(title_query: str, start: str | None = None,
                          end: str | None = None, summary: str | None = None,
                          time_min: str | None = None, time_max: str | None = None) -> dict:
    """Find an event by title keyword and reschedule/rename it."""
    try:
        event, response = _resolve_one(title_query, time_min, time_max)
        if response is not None:
            return response
        return update_event(event["id"], start=start, end=end, summary=summary)
    except HttpError as e:
        return {"error": f"Couldn't update the event (API {_status(e)})."}
