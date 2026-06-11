"""Thin Telegram adapter using long-polling (no public URL needed).

Kept deliberately small and dependency-light (raw HTTP via requests) so the
channel stays swappable: a WhatsApp adapter later implements the same two
operations (receive a message, send a message) without touching the agent loop.
"""
import requests

API = "https://api.telegram.org/bot{token}/{method}"


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
        # Telegram caps messages at 4096 chars; split long replies.
        for i in range(0, len(text), 4000):
            self._call("sendMessage", chat_id=chat_id, text=text[i:i + 4000])
