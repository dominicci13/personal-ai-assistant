"""Tests for the message-routing glue in main (mocked channel)."""
from unittest.mock import MagicMock

from assistant import main
from assistant.channel.telegram import IncomingMessage


def test_text_passes_through():
    msg = IncomingMessage(1, 1, 1, kind="text", text="block my Friday")
    assert main._to_agent_content(msg, MagicMock()) == "block my Friday"


def test_voice_is_transcribed(monkeypatch):
    channel = MagicMock()
    channel.download_file.return_value = b"ogg-bytes"
    monkeypatch.setattr(main, "transcribe", lambda audio: "what's on my calendar")
    msg = IncomingMessage(1, 1, 1, kind="voice", file_id="v1")
    assert main._to_agent_content(msg, channel) == "what's on my calendar"


def test_photo_builds_image_block_with_caption():
    channel = MagicMock()
    channel.download_file.return_value = b"\xff\xd8jpegbytes"
    msg = IncomingMessage(1, 1, 1, kind="photo", text="is this a good logo?", file_id="p1")
    content = main._to_agent_content(msg, channel)
    assert content[0]["type"] == "image"
    assert content[0]["source"]["media_type"] == "image/jpeg"
    assert content[1] == {"type": "text", "text": "is this a good logo?"}


def test_photo_without_caption_is_image_only():
    channel = MagicMock()
    channel.download_file.return_value = b"jpegbytes"
    msg = IncomingMessage(1, 1, 1, kind="photo", file_id="p1")
    content = main._to_agent_content(msg, channel)
    assert len(content) == 1 and content[0]["type"] == "image"


def test_unsupported_returns_none():
    msg = IncomingMessage(1, 1, 1, kind="unsupported")
    assert main._to_agent_content(msg, MagicMock()) is None
