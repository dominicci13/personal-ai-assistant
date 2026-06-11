"""Voice transcription via OpenAI Whisper.

Telegram voice notes are OGG/Opus, which Whisper accepts directly. A spoken command
becomes text that flows into the same agent loop as a typed message. (Only embeddings
and transcription use OpenAI; Claude stays the brain.)
"""
from __future__ import annotations

import io
from functools import lru_cache

from openai import OpenAI

from assistant.config import settings

TRANSCRIBE_MODEL = "whisper-1"


@lru_cache(maxsize=1)
def _client() -> OpenAI:
    """Build the OpenAI client once, failing loudly if the key is missing."""
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is not set — required for voice transcription.")
    return OpenAI(api_key=settings.openai_api_key)


def transcribe(audio: bytes, filename: str = "voice.ogg") -> str:
    """Transcribe audio bytes to text.

    Args:
        audio: Raw audio bytes (Telegram voice notes are OGG/Opus).
        filename: A name with an extension Whisper recognizes (drives format detection).

    Returns:
        The transcribed text (stripped).
    """
    buffer = io.BytesIO(audio)
    buffer.name = filename  # the OpenAI SDK uses the name's extension to detect format
    response = _client().audio.transcriptions.create(model=TRANSCRIBE_MODEL, file=buffer)
    return response.text.strip()
