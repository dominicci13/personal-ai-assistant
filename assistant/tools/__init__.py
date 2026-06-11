"""Tool catalog + dispatcher.

Each tool = (1) an entry in TOOLS (the schema Claude sees) and (2) a branch in
dispatch_tool that actually runs it. Add a new tool by adding both. This is the
seam the whole assistant grows along (calendar, email, web search come later).
"""
from datetime import datetime, timezone

from assistant.tools.remember import remember

TOOLS = [
    {
        "name": "get_current_datetime",
        "description": "Return the current UTC date and time. Use when the user "
                       "asks about the date, time, or 'today'.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
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
        return {"utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    if name == "remember":
        return remember(chat_id, tool_input["content"], tool_input["kind"])
    return {"error": f"unknown tool: {name}"}
