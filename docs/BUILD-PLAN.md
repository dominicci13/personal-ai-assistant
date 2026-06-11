# Build Plan — Track A (custom personal assistant)

**Last updated:** 2026-06-10
**Where we are:** Phases 1 & 2 DONE. Phase 1 = 3-tier memory + remember() + caching + routing +
consolidation. Phase 2 = Google Calendar read/create/reschedule/delete (confirm-first, title-based
write tools, Sonnet-default routing); DoD verified live in Fantastical. Setup + map in `MEMORY.md`.

**Next up:** Phase 3 — Email (draft-only) across Gmail/Outlook/iCloud.

---

## The 3-tier memory model (the core of this phase)

The goal: the assistant knows Brian from the first message, learns continuously, and
stays cheap on tokens. The trick is that you only pay full price for the smallest tier.

### Tier 1 — Identity (stable, always in context, prompt-cached)
- A hand-written `data/IDENTITY.md`: who Brian is, how he behaves, likes/dislikes, how he
  works. Plus a small **curated profile** of durable learned preferences.
- Loaded into the **system prompt** and marked with Anthropic **prompt caching**
  (`cache_control: {"type": "ephemeral"}`). Sent every turn but billed ~10% on cache hits.
- Keep it SMALL and consolidated — this is the tier you pay for every message.
- `data/IDENTITY.md` is gitignored (personal). Ship `data/IDENTITY.example.md` as a template.

### Tier 2 — Learned facts (retrieved, not dumped)
- Everything Brian tells the assistant to remember that isn't a core preference.
- Stored in **Postgres + pgvector** (embeddings). On each turn, embed the user message and
  **retrieve only the top-k relevant facts** to inject — never the whole store.
- This IS the portfolio RAG layer (project #2). Build it from primitives (no LangChain):
  OpenAI/Voyage/Anthropic embeddings → pgvector cosine search → inject top-k.

### Tier 3 — Conversation history (rolling window + summary)
- Keep the last N raw turns; periodically summarize older turns into a short recap and drop
  the raw ones. Replaces today's "last 40 messages" JSON approach.

### The `remember()` tool (continuous learning write path)
```
remember(content: str, kind: "preference" | "fact")
  kind="preference" -> update the curated profile in Tier 1 (small, consolidated, deduped)
  kind="fact"       -> embed + upsert into Tier 2 (pgvector)
```
- Fires whenever Brian says "remember…", "learn…", "from now on…".
- Add a periodic **consolidation pass** (merge duplicates, resolve contradictions, prune).
  The hard part of memory isn't writing — it's retrieval quality + consistency.

---

## Token-efficiency checklist (apply throughout)

- [ ] Prompt-cache the system block (IDENTITY + curated profile + tool definitions).
- [ ] Retrieve top-k from Tier 2; never inject the full store.
- [ ] Summarize Tier 3 history instead of carrying all raw turns.
- [ ] Route trivial/short turns to **Haiku**, reasoning turns to **Sonnet**.
- [ ] Trim/summarize large tool outputs before feeding them back into the loop.
- [ ] Log token usage per turn so spend is visible.

---

## Phased roadmap (each phase ends with something usable)

### Phase 1 — 3-tier memory + remember() + Postgres/pgvector  ✅ DONE
- Stand up Postgres + pgvector via docker-compose (local).
- Implement Tiers 1–3 and the `remember()` tool above.
- Turn on prompt caching + Haiku/Sonnet routing.
- **Definition of done:** "remember I prefer X" persists; later, an unrelated chat correctly
  recalls X via retrieval; identity is present from message one; token/turn is logged.

### Phase 2 — Calendar tools (Google + Outlook + iCloud)  ✅ DONE (Google; Outlook/iCloud later)
- Read + create events; verify they show in Fantastical. iCloud via CalDAV (fallback Google Tasks).
- **Done:** "what's on my calendar tomorrow", "block 3-4pm for X" work and show in Fantastical.

### Phase 3 — Email (draft-only) across Gmail + Outlook + iCloud  ← START HERE
- Read/summarize unread; draft tone-matched replies; **draft-and-confirm** send flow.
- **Done:** "summarize my unread", "draft a reply to X in my tone" → Brian approves before send.

### Phase 4 — Web research
- Search + fetch + compare; return ranked options with links. Stops at "here are the options."

### Phase 4.5 — Deploy (always-on)
- Move from local polling to the VPS (Hetzner) per the original BUILD-PLAN; add the webhook
  channel, restart resilience, Postgres backups. This restores "always-on/proactive."

### Phase 5 — Harden + live on it
- Monitoring, prompt refinement, add tools as needs surface, track spend.

---

## Out of scope here
Multi-tenant, billing, WhatsApp channel — those belong to the OpenClaw / product track.
