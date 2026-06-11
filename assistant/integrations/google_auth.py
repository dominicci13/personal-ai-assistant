"""Shared Google OAuth for all Google integrations (Calendar, Gmail, ...).

One installed-app browser consent (`run_google_auth.py`) writes `config/token.json`
with every scope below; each integration builds its own API service from
`get_credentials()`. Adding a Google capability = add its scope here and re-run the
consent once.
"""
from __future__ import annotations

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from assistant.config import settings

SCOPES = [
    "https://www.googleapis.com/auth/calendar.events",  # read + write calendar events
    "https://www.googleapis.com/auth/gmail.readonly",   # read mail (inbox, messages)
    "https://www.googleapis.com/auth/gmail.compose",     # create drafts (minimal scope for drafts)
]


def authorize() -> None:
    """Run the one-time browser consent flow and save the token with all SCOPES.

    Reads the OAuth client from ``config/credentials.json`` (downloaded from Google
    Cloud Console) and writes the token to ``config/token.json``. Re-run this after
    changing SCOPES so the new permissions are granted.

    Raises:
        FileNotFoundError: If ``credentials.json`` is missing — do the Google setup first.
    """
    if not settings.google_credentials_path.exists():
        raise FileNotFoundError(
            f"Missing {settings.google_credentials_path}. Download your OAuth "
            "'Desktop app' client from Google Cloud Console first (see the setup steps)."
        )
    flow = InstalledAppFlow.from_client_secrets_file(
        str(settings.google_credentials_path), SCOPES
    )
    creds = flow.run_local_server(port=0)
    settings.google_token_path.write_text(creds.to_json(), encoding="utf-8")


def get_credentials() -> Credentials:
    """Load saved credentials (shared by all Google services), refreshing if expired."""
    if not settings.google_token_path.exists():
        raise RuntimeError(
            "Google not authorized yet — run `python run_google_auth.py`."
        )
    creds = Credentials.from_authorized_user_file(str(settings.google_token_path), SCOPES)
    if not creds.valid and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        settings.google_token_path.write_text(creds.to_json(), encoding="utf-8")
    return creds
