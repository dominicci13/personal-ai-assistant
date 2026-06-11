"""Tests for voice transcription — mocked, no live API."""
from unittest.mock import MagicMock

from assistant.orchestrator import transcription


def test_transcribe_returns_stripped_text(monkeypatch):
    fake = MagicMock()
    fake.audio.transcriptions.create.return_value = MagicMock(text="  block my Friday  ")
    monkeypatch.setattr(transcription, "_client", lambda: fake)

    out = transcription.transcribe(b"fake-ogg-bytes")
    assert out == "block my Friday"

    _, kwargs = fake.audio.transcriptions.create.call_args
    assert kwargs["model"] == "whisper-1"
    assert kwargs["file"].name.endswith(".ogg")   # extension drives format detection
