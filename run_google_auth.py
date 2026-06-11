"""One-time Google Calendar authorization.

Opens a browser for consent and saves the refresh token to config/token.json.
Run once after placing config/credentials.json; re-run only if the token is
revoked or deleted.

Usage:  python run_google_auth.py
"""
from assistant.config import settings
from assistant.integrations.google_calendar import authorize


def main() -> None:
    authorize()
    print(f"Authorized — token saved to {settings.google_token_path}.")


if __name__ == "__main__":
    main()
