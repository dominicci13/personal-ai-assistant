# Runbook — Phase 0 (local)

Goal: have a working assistant on Telegram, running on your own machine, in ~30 min.
No VPS, domain, or webhook needed yet.

## 1. Create the Telegram bot (2 min)

1. In Telegram, open a chat with **@BotFather**.
2. Send `/newbot`. Pick a name and a username ending in `bot`.
3. BotFather replies with an **HTTP API token** like `123456789:ABC...`. Copy it.

## 2. Find your numeric user id (1 min)

1. In Telegram, open a chat with **@userinfobot** and send any message.
2. It replies with your **Id** (a number). Copy it. This is the only account
   allowed to use your assistant.

## 3. Get an Anthropic API key

1. console.anthropic.com → API keys → create key. Copy it.
2. Make sure the workspace has a little credit on it.

## 4. Configure

From the repo root:

```bash
cp .env.example .env
```

Edit `.env` and fill:
- `ANTHROPIC_API_KEY` = the key from step 3
- `TELEGRAM_BOT_TOKEN` = the token from step 1
- `ALLOWED_TELEGRAM_USER_ID` = your id from step 2

## 5. Install & run

```bash
python -m venv .venv
# Windows (PowerShell):
.venv\Scripts\Activate.ps1
# macOS/Linux:
# source .venv/bin/activate

pip install -r requirements.txt
python -m assistant.main
```

You should see: `Assistant running. Message your bot on Telegram.`

## 6. Test it

Message your bot:
- "What's the date and time?" → it calls `get_current_datetime`.
- "Remember that my gym is at 6pm." → it calls `save_note`.
- "What do you remember about me?" → it calls `recall_notes`.

If a different Telegram account messages the bot, it gets "Not authorized." — that's the allowlist working.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `Missing required env var` | A field in `.env` is empty. |
| `401` from Telegram | Wrong `TELEGRAM_BOT_TOKEN`. |
| Bot replies "Not authorized." to you | `ALLOWED_TELEGRAM_USER_ID` doesn't match your real id. |
| Anthropic auth error | Wrong/empty `ANTHROPIC_API_KEY` or no credit. |
| Nothing happens | The script must stay running in the terminal; closing it stops the bot. |

## What's next (Phase 1 proper)

- Swap the JSON memory for Postgres + pgvector (RAG recall over past chats).
- Add the first real tool group: calendar read/create across Google/Outlook/iCloud.
- Then email drafting (draft-only), then web research, then deploy to the VPS.
