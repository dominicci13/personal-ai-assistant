# Personal AI Assistant

A single-tenant personal assistant I talk to over Telegram. Claude is the brain;
a custom Python tool-use loop is the orchestrator. Built local-first, structured
to deploy to a VPS later without rewrites.

This repo doubles as a portfolio piece: agent-with-tools design + (soon) RAG
memory, built from primitives (no LangChain), with a swappable channel/tool model.

## Status

- **Phase 1 done (local):** Telegram long-polling → Claude tool-use loop → 3-tier memory → reply.
  Tier 1 identity (always in context), Tier 2 facts (Postgres + pgvector RAG), Tier 3 conversation
  (rolling window + summary). Plus the `remember()` tool, prompt caching, Haiku/Sonnet routing,
  per-turn token logging, and a memory-consolidation pass. Tools: `get_current_datetime`, `remember`.
- **Next:** Calendar tools (Google/Outlook/iCloud), then email, web research, then VPS deploy.

## Architecture

```
Telegram (long-poll)  ->  TelegramChannel (swappable adapter)
                              |
                              v
                      Orchestrator / agent loop (Claude + tools)
                              |  load memory -> call Claude -> run tools -> repeat -> reply
                              v
                      Tools: datetime | remember | ...later: calendar, email, web

Memory tiers: 1) identity (system prompt)  2) facts (pgvector RAG, retrieved top-k)
              3) conversation (recent turns verbatim + summarized tail)
```

The agent loop is the durable core. Channels and tools sit behind small
interfaces so adding WhatsApp or a new tool never touches the loop.

## Quick start

See `docs/RUNBOOK-Phase0.md` for the Telegram/Anthropic setup. Short version:

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                  # fill in the secrets (Anthropic, OpenAI, Telegram)
docker compose up -d                  # Postgres + pgvector for Tier 2 memory
python -m assistant.orchestrator.db   # one-time: create the facts table
python -m assistant.main
```

Message your bot on Telegram. Only the `ALLOWED_TELEGRAM_USER_ID` can use it.

## Layout

| Path | Role |
|---|---|
| `assistant/main.py` | Entry point: poll → agent → reply, with the user allowlist |
| `assistant/channel/telegram.py` | Telegram long-poll adapter (swappable) |
| `assistant/orchestrator/agent.py` | The Claude tool-use loop: model routing, recall injection, token logging |
| `assistant/orchestrator/identity.py` | Tier 1 — identity + curated profile → system prompt |
| `assistant/orchestrator/facts.py` | Tier 2 — pgvector RAG: store, retrieve, consolidate |
| `assistant/orchestrator/embeddings.py` | OpenAI `text-embedding-3-small` wrapper |
| `assistant/orchestrator/db.py` | Postgres + pgvector connection + schema |
| `assistant/orchestrator/memory.py` | Tier 3 — conversation window + running summary |
| `assistant/orchestrator/persona.py` | Base behavioral system prompt |
| `assistant/tools/` | Tool catalog + implementations (`remember`, `get_current_datetime`) |
| `docker-compose.yml` | Local Postgres + pgvector |
| `data/` | Runtime state, incl. `IDENTITY.md` (gitignored) |

## Author
Built by **Brian Ramirez** ([@dominicci13](https://github.com/dominicci13)) — automation & AI workflow specialist. More on my [GitHub profile](https://github.com/dominicci13) and [LinkedIn](https://linkedin.com/in/bdramirez).
