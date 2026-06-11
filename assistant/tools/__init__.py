"""Tool catalog + dispatcher.

Each tool = (1) an entry in TOOLS (the schema Claude sees) and (2) a branch in
dispatch_tool that actually runs it. Add a new tool by adding both. This is the
seam the whole assistant grows along (calendar, email, web search come later).
"""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from assistant.config import settings
from assistant.tools.calendar import (
    create_calendar_event,
    delete_calendar_event,
    list_calendar_events,
    update_calendar_event,
)
from assistant.tools.remember import remember

TOOLS = [
    {
        "name": "get_current_datetime",
        "description": "Return the current date and time in UTC and Brian's local "
                       "timezone, plus today's weekday and date. Use for date/time "
                       "questions and ALWAYS before resolving a day name or relative "
                       "date ('Thursday', 'tomorrow', 'next week') so you compute the "
                       "right target date.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "list_calendar_events",
        "description": (
            "List Brian's Google Calendar events between two timestamps. To resolve a "
            "relative range ('tomorrow', 'this week'), first call get_current_datetime, "
            "then pass time_min and time_max as RFC3339 timestamps WITH his timezone "
            "offset, e.g. '2026-06-12T00:00:00-04:00'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "time_min": {"type": "string", "description": "Range start, RFC3339 with offset."},
                "time_max": {"type": "string", "description": "Range end, RFC3339 with offset."},
            },
            "required": ["time_min", "time_max"],
        },
    },
    {
        "name": "create_calendar_event",
        "description": (
            "Create an event on Brian's Google Calendar. IMPORTANT: before calling "
            "this, restate the event you parsed (title, date, start-end time with "
            "timezone) and wait for Brian's explicit confirmation in chat — only call "
            "after he says yes. Provide start/end as RFC3339 timestamps WITH his "
            "timezone offset (use get_current_datetime to resolve relative dates)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "Event title."},
                "start": {"type": "string", "description": "Start, RFC3339 with offset."},
                "end": {"type": "string", "description": "End, RFC3339 with offset."},
                "description": {"type": "string", "description": "Optional event notes."},
            },
            "required": ["summary", "start", "end"],
        },
    },
    {
        "name": "delete_calendar_event",
        "description": (
            "Delete an event from Brian's Google Calendar. The tool finds the event "
            "itself by title keyword — you do NOT need an id. Pass title_query (a word "
            "or two from the event title); optionally narrow with time_min/time_max "
            "(RFC3339 with offset). Restate which event you'll delete and wait for "
            "Brian's explicit confirmation before calling. If it returns "
            "needs_disambiguation, ask Brian which one and retry with a narrower query."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title_query": {"type": "string", "description": "Keyword(s) from the event title, e.g. 'client call'."},
                "time_min": {"type": "string", "description": "Optional search start, RFC3339 with offset."},
                "time_max": {"type": "string", "description": "Optional search end, RFC3339 with offset."},
            },
            "required": ["title_query"],
        },
    },
    {
        "name": "update_calendar_event",
        "description": (
            "Reschedule or rename an event (e.g. 'move my 3pm call to 4pm'). The tool "
            "finds the event itself by title keyword — no id needed. Pass title_query "
            "plus only the fields that change: new start/end (RFC3339 with offset) "
            "and/or a new summary; optionally narrow with time_min/time_max. Restate "
            "the change and wait for Brian's explicit confirmation before calling. If "
            "it returns needs_disambiguation, ask which one."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title_query": {"type": "string", "description": "Keyword(s) from the event's current title."},
                "start": {"type": "string", "description": "New start, RFC3339 with offset (omit if unchanged)."},
                "end": {"type": "string", "description": "New end, RFC3339 with offset (omit if unchanged)."},
                "summary": {"type": "string", "description": "New title (omit if unchanged)."},
                "time_min": {"type": "string", "description": "Optional search start, RFC3339 with offset."},
                "time_max": {"type": "string", "description": "Optional search end, RFC3339 with offset."},
            },
            "required": ["title_query"],
        },
    },
    {
        "name": "remember",
        "description": (
            "Save a durable fact or preference about the user to long-term memory "
            "so you can recall it in future, unrelated conversations. Call this when "
            "the user says 'remember…', 'from now on…', 'note that…', or states a "
            "lasting fact about themselves (their preferences, people, projects, "
            "schedule). Do NOT call it for one-off chit-chat or transient context."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "The thing to remember, as a clear standalone "
                                   "sentence (e.g. 'Brian's gym is at 6pm').",
                },
                "kind": {
                    "type": "string",
                    "enum": ["fact", "preference"],
                    "description": "'preference' for a durable like/dislike or "
                                   "working style; 'fact' for anything else.",
                },
            },
            "required": ["content", "kind"],
        },
    },
]


def dispatch_tool(name: str, tool_input: dict, chat_id: int) -> dict:
    """Route a tool call to its implementation. Always returns a JSON-able dict."""
    if name == "get_current_datetime":
        now = datetime.now(timezone.utc)
        local = now.astimezone(ZoneInfo(settings.calendar_timezone))
        return {
            "utc": now.isoformat(timespec="seconds"),
            "local": local.isoformat(timespec="seconds"),
            "timezone": settings.calendar_timezone,
            # Weekday + date spelled out so Claude doesn't have to compute the day
            # name from the date (a frequent source of "Thursday -> wrong date" errors).
            "today": local.strftime("%A, %Y-%m-%d"),
            "weekday": local.strftime("%A"),
        }
    if name == "remember":
        return remember(chat_id, tool_input["content"], tool_input["kind"])
    if name == "list_calendar_events":
        return list_calendar_events(tool_input["time_min"], tool_input["time_max"])
    if name == "create_calendar_event":
        return create_calendar_event(
            tool_input["summary"], tool_input["start"], tool_input["end"],
            tool_input.get("description"),
        )
    if name == "delete_calendar_event":
        return delete_calendar_event(
            tool_input["title_query"], tool_input.get("time_min"), tool_input.get("time_max"),
        )
    if name == "update_calendar_event":
        return update_calendar_event(
            tool_input["title_query"], tool_input.get("start"), tool_input.get("end"),
            tool_input.get("summary"), tool_input.get("time_min"), tool_input.get("time_max"),
        )
    return {"error": f"unknown tool: {name}"}
