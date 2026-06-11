"""Entry point: long-poll Telegram, run the agent, reply. Ctrl+C to stop.

Run from the repo root:  python -m assistant.main
"""
from assistant.config import settings
from assistant.channel.telegram import TelegramChannel
from assistant.orchestrator.agent import run_turn


def main():
    channel = TelegramChannel(settings.telegram_bot_token)
    offset = None
    print("Assistant running. Message your bot on Telegram. Ctrl+C to stop.")
    while True:
        for update_id, from_id, chat_id, text in channel.get_updates(offset):
            offset = update_id + 1  # acknowledge so we don't reprocess it

            # Allowlist: Telegram bots are public by handle, so reject everyone
            # except Brian. This is mandatory, not optional.
            if from_id != settings.allowed_telegram_user_id:
                channel.send_message(chat_id, "Not authorized.")
                continue

            try:
                reply = run_turn(chat_id, text)
            except Exception as exc:  # never let one bad turn kill the loop
                reply = f"Error handling that: {exc}"
            channel.send_message(chat_id, reply)


if __name__ == "__main__":
    main()
