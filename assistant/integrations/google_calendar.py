"""Google Calendar integration: read/create/update/delete event wrappers.

OAuth is shared across Google integrations — see ``google_auth.py``. This module
just builds the Calendar service and shapes events for the agent.
"""
from __future__ import annotations

from googleapiclient.discovery import build

from assistant.config import settings
from assistant.integrations.google_auth import get_credentials


def get_service():
    """Return an authenticated Google Calendar API service client (v3)."""
    return build("calendar", "v3", credentials=get_credentials(), cache_discovery=False)


def _format_event(raw: dict) -> dict:
    """Reduce a Google event resource to the fields we care about.

    Handles both timed events (``start.dateTime``) and all-day events
    (``start.date``).
    """
    start = raw["start"].get("dateTime", raw["start"].get("date"))
    end = raw["end"].get("dateTime", raw["end"].get("date"))
    return {
        "id": raw["id"],
        "summary": raw.get("summary", "(no title)"),
        "start": start,
        "end": end,
        "location": raw.get("location"),
        "all_day": "date" in raw["start"],
    }


def list_events(time_min: str, time_max: str, calendar_id: str = "primary",
                max_results: int = 25) -> list[dict]:
    """List events between two RFC3339 timestamps, earliest first.

    Args:
        time_min: Lower bound, RFC3339 with offset (e.g. ``2026-06-12T00:00:00-04:00``).
        time_max: Upper bound, same format.
        calendar_id: Which calendar (``"primary"`` is the user's main one).
        max_results: Cap on events returned.

    Returns:
        A list of simplified event dicts (see ``_format_event``), recurring events
        expanded into individual instances.
    """
    resp = (
        get_service()
        .events()
        .list(
            calendarId=calendar_id,
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,   # expand recurring events into instances
            orderBy="startTime",
            maxResults=max_results,
        )
        .execute()
    )
    return [_format_event(e) for e in resp.get("items", [])]


def create_event(summary: str, start: str, end: str, timezone: str | None = None,
                 description: str | None = None, calendar_id: str = "primary") -> dict:
    """Create a timed event and return its key details.

    Args:
        summary: Event title.
        start: Start time, RFC3339 with offset (e.g. ``2026-06-17T15:00:00-04:00``).
        end: End time, same format.
        timezone: IANA tz for the event; defaults to ``settings.calendar_timezone``.
        description: Optional event body.
        calendar_id: Which calendar to write to (``"primary"`` by default).

    Returns:
        ``{"id", "summary", "start", "end", "link"}`` for the created event.
    """
    body = {
        "summary": summary,
        "start": {"dateTime": start, "timeZone": timezone or settings.calendar_timezone},
        "end": {"dateTime": end, "timeZone": timezone or settings.calendar_timezone},
    }
    if description:
        body["description"] = description

    created = get_service().events().insert(calendarId=calendar_id, body=body).execute()
    return {
        "id": created["id"],
        "summary": created.get("summary"),
        "start": created["start"].get("dateTime"),
        "end": created["end"].get("dateTime"),
        "link": created.get("htmlLink"),
    }


def delete_event(event_id: str, calendar_id: str = "primary") -> dict:
    """Delete an event by id (the id comes from ``list_events``).

    Args:
        event_id: The event's id, as returned by ``list_events``/``_format_event``.
        calendar_id: Which calendar the event lives on.

    Returns:
        ``{"deleted": True, "id": event_id}``. (The API returns 204/no body.)
    """
    get_service().events().delete(calendarId=calendar_id, eventId=event_id).execute()
    return {"deleted": True, "id": event_id}


def update_event(event_id: str, start: str | None = None, end: str | None = None,
                 summary: str | None = None, timezone: str | None = None,
                 calendar_id: str = "primary") -> dict:
    """Patch an existing event (reschedule and/or rename); only given fields change.

    Args:
        event_id: The event's id (from ``list_events``).
        start: New start, RFC3339 with offset (omit to leave unchanged).
        end: New end, RFC3339 with offset (omit to leave unchanged).
        summary: New title (omit to leave unchanged).
        timezone: IANA tz for new times; defaults to ``settings.calendar_timezone``.
        calendar_id: Which calendar the event lives on.

    Returns:
        ``{"id", "summary", "start", "end", "link"}`` for the updated event.
    """
    tz = timezone or settings.calendar_timezone
    body: dict = {}
    if summary is not None:
        body["summary"] = summary
    if start is not None:
        body["start"] = {"dateTime": start, "timeZone": tz}
    if end is not None:
        body["end"] = {"dateTime": end, "timeZone": tz}

    updated = (
        get_service().events()
        .patch(calendarId=calendar_id, eventId=event_id, body=body)
        .execute()
    )
    return {
        "id": updated["id"],
        "summary": updated.get("summary"),
        "start": updated["start"].get("dateTime"),
        "end": updated["end"].get("dateTime"),
        "link": updated.get("htmlLink"),
    }
