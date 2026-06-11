"""Tests for the Google Calendar integration — mocked, no live API calls."""
from unittest.mock import MagicMock

from assistant.integrations import google_calendar


def test_format_event_timed():
    raw = {
        "id": "abc",
        "summary": "Standup",
        "start": {"dateTime": "2026-06-12T09:00:00-04:00"},
        "end": {"dateTime": "2026-06-12T09:30:00-04:00"},
        "location": "Zoom",
    }
    assert google_calendar._format_event(raw) == {
        "id": "abc",
        "summary": "Standup",
        "start": "2026-06-12T09:00:00-04:00",
        "end": "2026-06-12T09:30:00-04:00",
        "location": "Zoom",
        "all_day": False,
    }


def test_format_event_all_day_and_missing_title():
    raw = {"id": "d1", "start": {"date": "2026-06-12"}, "end": {"date": "2026-06-13"}}
    out = google_calendar._format_event(raw)
    assert out["summary"] == "(no title)"   # missing title -> placeholder
    assert out["all_day"] is True           # date (not dateTime) -> all-day
    assert out["location"] is None


def test_list_events_formats_results_and_passes_query_params(monkeypatch):
    captured = {}

    def fake_list(**kwargs):
        captured.update(kwargs)
        result = MagicMock()
        result.execute.return_value = {
            "items": [{
                "id": "1", "summary": "A",
                "start": {"dateTime": "2026-06-12T10:00:00-04:00"},
                "end": {"dateTime": "2026-06-12T11:00:00-04:00"},
            }]
        }
        return result

    fake_service = MagicMock()
    fake_service.events.return_value.list.side_effect = fake_list
    monkeypatch.setattr(google_calendar, "get_service", lambda: fake_service)

    events = google_calendar.list_events(
        "2026-06-12T00:00:00-04:00", "2026-06-13T00:00:00-04:00"
    )

    assert len(events) == 1 and events[0]["summary"] == "A"
    # query is built correctly: recurring expanded, sorted, primary calendar
    assert captured["singleEvents"] is True
    assert captured["orderBy"] == "startTime"
    assert captured["calendarId"] == "primary"
    assert captured["timeMin"] == "2026-06-12T00:00:00-04:00"


def test_create_event_builds_body_and_defaults_timezone(monkeypatch):
    captured = {}

    def fake_insert(**kwargs):
        captured.update(kwargs)
        body = kwargs["body"]
        result = MagicMock()
        result.execute.return_value = {
            "id": "evt123",
            "summary": body["summary"],
            "start": {"dateTime": body["start"]["dateTime"]},
            "end": {"dateTime": body["end"]["dateTime"]},
            "htmlLink": "https://cal.example/evt123",
        }
        return result

    fake_service = MagicMock()
    fake_service.events.return_value.insert.side_effect = fake_insert
    monkeypatch.setattr(google_calendar, "get_service", lambda: fake_service)

    out = google_calendar.create_event(
        "Deep work", "2026-06-17T15:00:00-04:00", "2026-06-17T16:00:00-04:00",
        description="focus block",
    )

    body = captured["body"]
    assert body["summary"] == "Deep work"
    assert body["start"]["dateTime"] == "2026-06-17T15:00:00-04:00"
    assert body["start"]["timeZone"] == "America/Santo_Domingo"  # defaulted from settings
    assert body["description"] == "focus block"
    assert captured["calendarId"] == "primary"
    assert out["id"] == "evt123"
    assert out["link"] == "https://cal.example/evt123"


def test_delete_event_calls_api_with_id(monkeypatch):
    captured = {}

    def fake_delete(**kwargs):
        captured.update(kwargs)
        result = MagicMock()
        result.execute.return_value = ""   # the API returns no body
        return result

    fake_service = MagicMock()
    fake_service.events.return_value.delete.side_effect = fake_delete
    monkeypatch.setattr(google_calendar, "get_service", lambda: fake_service)

    out = google_calendar.delete_event("evt123")
    assert captured == {"calendarId": "primary", "eventId": "evt123"}
    assert out == {"deleted": True, "id": "evt123"}


def test_update_event_patches_only_given_fields(monkeypatch):
    captured = {}

    def fake_patch(**kwargs):
        captured.update(kwargs)
        body = kwargs["body"]
        result = MagicMock()
        result.execute.return_value = {
            "id": "e1", "summary": body.get("summary", "old title"),
            "start": {"dateTime": body["start"]["dateTime"]},
            "end": {"dateTime": body["end"]["dateTime"]},
            "htmlLink": "https://cal.example/e1",
        }
        return result

    fake_service = MagicMock()
    fake_service.events.return_value.patch.side_effect = fake_patch
    monkeypatch.setattr(google_calendar, "get_service", lambda: fake_service)

    out = google_calendar.update_event(
        "e1", start="2026-06-16T16:00:00-04:00", end="2026-06-16T17:00:00-04:00"
    )
    body = captured["body"]
    assert "summary" not in body                       # omitted -> not patched
    assert body["start"]["dateTime"] == "2026-06-16T16:00:00-04:00"
    assert body["start"]["timeZone"] == "America/Santo_Domingo"
    assert captured["eventId"] == "e1"
    assert out["id"] == "e1"


def _evt(summary, eid="abc"):
    return {"id": eid, "summary": summary, "start": "2026-06-18T15:00:00-04:00",
            "end": "2026-06-18T16:00:00-04:00", "location": None, "all_day": False}


def test_delete_tool_no_match_returns_error(monkeypatch):
    from assistant.tools import calendar as cal
    monkeypatch.setattr(cal, "list_events", lambda *a, **k: [])
    out = cal.delete_calendar_event("client call")
    assert "error" in out and "No event matching" in out["error"]


def test_delete_tool_resolves_by_title_and_deletes(monkeypatch):
    from assistant.tools import calendar as cal
    monkeypatch.setattr(cal, "list_events", lambda *a, **k: [_evt("Client call", eid="real123")])
    deleted = {}
    monkeypatch.setattr(cal, "delete_event",
                        lambda eid: deleted.update(id=eid) or {"deleted": True, "id": eid})
    out = cal.delete_calendar_event("client call")
    assert deleted["id"] == "real123"          # used the REAL id resolved from the title
    assert out["deleted"] is True and out["summary"] == "Client call"


def test_delete_tool_disambiguation_when_multiple(monkeypatch):
    from assistant.tools import calendar as cal
    monkeypatch.setattr(cal, "list_events", lambda *a, **k:
                        [_evt("Client call", eid="1"), _evt("Client call follow-up", eid="2")])
    out = cal.delete_calendar_event("client call")
    assert "needs_disambiguation" in out and len(out["needs_disambiguation"]) == 2
