"""Entry point: long-poll Telegram, run the agent, reply. Ctrl+C to stop.

Run from the repo root:  python -m assistant.main
"""
import base64

from assistant.channel.telegram import TelegramChannel
from assistant.config import settings
from assistant.orchestrator.agent import run_turn
from assistant.orchestrator.transcription import transcribe


def _to_agent_content(msg, channel):
    """Convert an incoming Telegram message into agent content, or None if unsupported.

    text  -> the text string
    voice -> transcribed text (Whisper)
    photo -> [image block, + caption block if there's a caption]
    """
    if msg.kind == "text":
        return msg.text
    if msg.kind == "voice":
        return transcribe(channel.download_file(msg.file_id))
    if msg.kind == "photo":
        data = base64.standard_b64encode(channel.download_file(msg.file_id)).decode()
        blocks = [{"type": "image",
                   "source": {"type": "base64", "media_type": "image/jpeg", "data": data}}]
        if msg.text:  # the photo's caption, if any
            blocks.append({"type": "text", "text": msg.text})
        return blocks
    return None


def main():
    channel = TelegramChannel(settings.telegram_bot_token)
    offset = None
    print("Assistant running. Message your bot on Telegram. Ctrl+C to stop.")
    while True:
        for msg in channel.get_updates(offset):
            offset = msg.update_id + 1  # acknowledge so we don't reprocess it

            # Allowlist: Telegram bots are public by handle, so reject everyone
            # except Brian. This is mandatory, not optional.
            if msg.from_id != settings.allowed_telegram_user_id:
                channel.send_message(msg.chat_id, "Not authorized.")
                continue

            try:
                content = _to_agent_content(msg, channel)
                if content is None:
                    channel.send_message(
                        msg.chat_id, "Sorry, I can only handle text, voice notes, and photos."
                    )
                    continue
                reply = run_turn(msg.chat_id, content)
            except Exception as exc:  # never let one bad turn kill the loop
                reply = f"Error handling that: {exc}"
            channel.send_message(msg.chat_id, reply)


if __name__ == "__main__":
    main()
