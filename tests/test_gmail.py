"""Tests for the Gmail integration — mocked, no live API calls."""
import base64
from unittest.mock import MagicMock

from assistant.integrations import gmail


def _b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode()


def test_header_case_insensitive_and_missing():
    headers = [{"name": "From", "value": "a@b.com"}, {"name": "Subject", "value": "Hi"}]
    assert gmail._header(headers, "from") == "a@b.com"
    assert gmail._header(headers, "Subject") == "Hi"
    assert gmail._header(headers, "Cc") == ""


def test_extract_body_plain_single_part():
    payload = {"mimeType": "text/plain", "body": {"data": _b64("hello world")}}
    assert gmail._extract_body(payload) == "hello world"


def test_extract_body_prefers_plain_in_multipart():
    payload = {
        "mimeType": "multipart/alternative",
        "body": {},
        "parts": [
            {"mimeType": "text/plain", "body": {"data": _b64("plain version")}},
            {"mimeType": "text/html", "body": {"data": _b64("<b>html version</b>")}},
        ],
    }
    assert gmail._extract_body(payload) == "plain version"


def test_extract_body_falls_back_to_stripped_html_when_no_plain():
    payload = {"mimeType": "text/html", "body": {"data": _b64("<p>only <b>html</b></p>")}}
    assert gmail._extract_body(payload) == "only html"   # tags stripped to text


def test_list_unread_formats_summaries(monkeypatch):
    def fake_get(userId, id, format, metadataHeaders):
        result = MagicMock()
        result.execute.return_value = {
            "id": id, "threadId": "t-" + id, "snippet": "a short preview",
            "payload": {"headers": [
                {"name": "From", "value": "Jane <jane@co.com>"},
                {"name": "Subject", "value": "Quick question"},
                {"name": "Date", "value": "Wed, 11 Jun 2026 09:00:00 -0400"},
            ]},
        }
        return result

    def fake_list(**kwargs):
        result = MagicMock()
        result.execute.return_value = {"messages": [{"id": "m1"}]}
        return result

    service = MagicMock()
    service.users.return_value.messages.return_value.list.side_effect = fake_list
    service.users.return_value.messages.return_value.get.side_effect = fake_get
    monkeypatch.setattr(gmail, "get_service", lambda: service)

    out = gmail.list_unread(max_results=5)
    assert len(out) == 1
    assert out[0] == {
        "id": "m1", "thread_id": "t-m1", "from": "Jane <jane@co.com>",
        "subject": "Quick question", "date": "Wed, 11 Jun 2026 09:00:00 -0400",
        "snippet": "a short preview",
    }


def test_create_draft_new_builds_message(monkeypatch):
    captured = {}

    def fake_create(userId, body):
        captured.update(body)
        result = MagicMock()
        result.execute.return_value = {"id": "draft1"}
        return result

    service = MagicMock()
    service.users.return_value.drafts.return_value.create.side_effect = fake_create
    monkeypatch.setattr(gmail, "get_service", lambda: service)

    out = gmail.create_draft_new("bob@x.com", "Hello", "Hi Bob,\nThanks.")
    assert out == {"draft_id": "draft1", "to": "bob@x.com", "subject": "Hello"}
    raw = base64.urlsafe_b64decode(captured["message"]["raw"]).decode()
    assert "To: bob@x.com" in raw
    assert "Subject: Hello" in raw
    assert "Thanks." in raw
    assert "threadId" not in captured["message"]   # a fresh draft, not a thread


def test_create_draft_reply_threads_correctly(monkeypatch):
    def fake_get(userId, id, format, metadataHeaders):
        result = MagicMock()
        result.execute.return_value = {
            "threadId": "thread99",
            "payload": {"headers": [
                {"name": "From", "value": "Jane <jane@co.com>"},
                {"name": "Subject", "value": "Project update"},
                {"name": "Message-ID", "value": "<orig123@mail>"},
            ]},
        }
        return result

    captured = {}

    def fake_create(userId, body):
        captured.update(body)
        result = MagicMock()
        result.execute.return_value = {"id": "draft2"}
        return result

    service = MagicMock()
    service.users.return_value.messages.return_value.get.side_effect = fake_get
    service.users.return_value.drafts.return_value.create.side_effect = fake_create
    monkeypatch.setattr(gmail, "get_service", lambda: service)

    out = gmail.create_draft_reply("m1", "Sounds good.")
    assert out["to"] == "Jane <jane@co.com>"
    assert out["subject"] == "Re: Project update"      # Re: prefix added
    assert captured["message"]["threadId"] == "thread99"
    raw = base64.urlsafe_b64decode(captured["message"]["raw"]).decode()
    assert "In-Reply-To: <orig123@mail>" in raw        # threads in the client
    assert "To: Jane <jane@co.com>" in raw
    assert "Sounds good." in raw
