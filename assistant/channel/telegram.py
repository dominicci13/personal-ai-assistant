"""Thin Telegram adapter using long-polling (no public URL needed).

Kept deliberately small and dependency-light (raw HTTP via requests) so the
channel stays swappable: a WhatsApp adapter later implements the same two
operations (receive a message, send a message) without touching the agent loop.
"""
import html
import re

import requests

API = "https://api.telegram.org/bot{token}/{method}"


def _to_telegram_html(text: str) -> str:
    """Render Claude's markdown as Telegram-supported HTML.

    Telegram only formats messages sent with parse_mode="HTML" (or Markdown); plain
    text shows the raw ``**``. We escape HTML-special chars first, then map the
    markdown Claude actually emits: ``**bold**`` -> <b>, `` `code` `` -> <code>, and
    drop ``#`` header markers (kept bold via the surrounding ``**`` Claude usually adds).
    """
    text = html.escape(text, quote=False)                       # & < >  ->  entities
    text = re.sub(r"(?m)^\s*#{1,6}\s*", "", text)               # drop "# " header marks
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text, flags=re.DOTALL)
    text = re.sub(r"`([^`\n]+?)`", r"<code>\1</code>", text)
    return text


def _strip_markdown(text: str) -> str:
    """Plain-text fallback: remove markdown markers (no HTML, can't fail to parse)."""
    text = re.sub(r"(?m)^\s*#{1,6}\s*", "", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text, flags=re.DOTALL)
    text = re.sub(r"`([^`\n]+?)`", r"\1", text)
    return text


class TelegramChannel:
    def __init__(self, token: str):
        self._token = token

    def _call(self, method: str, **params):
        url = API.format(token=self._token, method=method)
        # 30s server-side long poll; give requests a bit more before timing out.
        resp = requests.post(url, json=params, timeout=40)
        resp.raise_for_status()
        return resp.json()["result"]

    def get_updates(self, offset: int | None = None, timeout: int = 30):
        """Yield (update_id, from_user_id, chat_id, text) for new text messages."""
        params = {"timeout": timeout, "allowed_updates": ["message"]}
        if offset is not None:
            params["offset"] = offset
        for upd in self._call("getUpdates", **params):
            msg = upd.get("message")
            if not msg or "text" not in msg:
                continue
            yield (upd["update_id"], msg["from"]["id"], msg["chat"]["id"], msg["text"])

    def send_message(self, chat_id: int, text: str):
        # Telegram caps messages at 4096 chars; split long replies. Render markdown
        # as HTML; if a chunk's tags are unbalanced (e.g. a **bold** split across the
        # 4000-char boundary), Telegram 400s — fall back to plain text for that chunk.
        for i in range(0, len(text), 4000):
            chunk = text[i:i + 4000]
            try:
                self._call("sendMessage", chat_id=chat_id,
                           text=_to_telegram_html(chunk), parse_mode="HTML")
            except requests.HTTPError:
                self._call("sendMessage", chat_id=chat_id, text=_strip_markdown(chunk))
