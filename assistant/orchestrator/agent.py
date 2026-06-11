"""The brain: a Claude tool-use loop. This is the durable core of the product."""
import json
import re

from anthropic import Anthropic

from assistant.config import settings
from assistant.orchestrator.memory import ConversationMemory
from assistant.orchestrator.identity import build_system_prompt
from assistant.orchestrator.facts import retrieve_top_k
from assistant.tools import TOOLS, dispatch_tool

_client = Anthropic(api_key=settings.anthropic_api_key)

# Tier 2 recall tuning. We measured that with text-embedding-3-small, naturally
# phrased relevant queries land around cosine distance 0.7-0.75 while unrelated
# facts are only a little further (~0.79) — too narrow a gap for a tight cutoff to
# separate them. So we retrieve the few nearest facts and let Claude judge relevance
# (the injected note says "ignore if not"), keeping the distance filter only as a
# loose sanity backstop to drop pathologically-distant matches once the store grows.
RECALL_K = 3
RECALL_MAX_DISTANCE = 0.85


def _recall_note(chat_id: int, query: str) -> str:
    """Build an injectable note of Tier 2 facts relevant to ``query`` (or '').

    Best-effort by design: a retrieval error returns '' so the turn still proceeds
    — memory is an enhancement, never the critical path.
    """
    try:
        hits = retrieve_top_k(chat_id, query, k=RECALL_K)
    except Exception as exc:
        print(f"[memory] recall skipped: {exc}")
        return ""
    relevant = [h for h in hits if h["distance"] <= RECALL_MAX_DISTANCE]
    if not relevant:
        return ""
    lines = "\n".join(f"- {h['content']}" for h in relevant)
    return "Relevant things you've saved about Brian (use if helpful, ignore if not):\n" + lines


# Haiku is only safe for trivial pleasantries that never trigger a tool. Everything
# else — actions, questions, confirmations, follow-ups — goes to Sonnet, because
# calendar/memory tool use and date reasoning are exactly where the small model
# hallucinates (claims "Done" without calling the tool; botches weekday math).
_TRIVIAL = re.compile(
    r"^(hi|hey|hello|thanks|thank you|cool|nice|great|perfect|awesome|got it|np)\b",
    re.IGNORECASE,
)


def choose_model(user_text: str) -> str:
    """Pick the model: Haiku only for short pure pleasantries, Sonnet for the rest.

    Biased toward Sonnet on purpose — for a personal assistant, correct tool use
    beats the small token savings of routing real requests to the weaker model.
    """
    text = user_text.strip()
    if len(text.split()) <= 4 and "?" not in text and _TRIVIAL.match(text):
        return settings.model_routing   # Haiku — small talk only
    return settings.model_reasoning      # Sonnet — anything that may need tools/reasoning


def _log_usage(model: str, totals: dict) -> None:
    """Print a one-line token report for the turn so spend stays visible."""
    name = "haiku " if model == settings.model_routing else "sonnet"
    print(
        f"[turn] model={name} in={totals['input']:>4} out={totals['output']:>4} "
        f"cache_read={totals['cache_read']:>4} cache_write={totals['cache_write']:>4}"
    )


def run_turn(chat_id: int, user_text: str) -> str:
    """Handle one user message end-to-end; return the assistant's final text."""
    memory = ConversationMemory(chat_id, settings.data_dir)

    # Persisted history is plain {role, content:str}; load it as the base context.
    history = memory.load()
    # `working` is the live message list passed to the API; it may temporarily
    # hold tool_use/tool_result blocks and injected memory that we do NOT persist.
    working = [dict(m) for m in history]

    # Tier 2 recall: inject facts relevant to THIS message as ephemeral context.
    # It goes into `working` only (never `history`), so the rolling conversation
    # file stays clean and the injected note doesn't compound over turns.
    note = _recall_note(chat_id, user_text)
    if note:
        working.append({"role": "user", "content": [
            {"type": "text", "text": note},
            {"type": "text", "text": user_text},
        ]})
    else:
        working.append({"role": "user", "content": user_text})

    model = choose_model(user_text)
    totals = {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0}

    while True:
        resp = _client.messages.create(
            model=model,
            max_tokens=2048,  # room for multi-option research answers with links
            # cache_control marks the stable prefix (tools render first, then this
            # system block) so repeated turns bill it at ~10%. Measured: caching
            # engages above ~2048 tokens (Sonnet 4.6's minimum) — at ~4.5k tokens it
            # reads the whole prefix from cache. Our block is ~1.3k tokens today, so
            # it doesn't engage YET; it self-activates once Phase 2 tools grow the
            # prefix past the minimum. Harmless to leave on until then.
            system=[{
                "type": "text",
                "text": build_system_prompt(),
                "cache_control": {"type": "ephemeral"},
            }],
            tools=TOOLS,
            messages=working,
        )
        # Echo the assistant turn back into the working context (raw blocks).
        u = resp.usage
        totals["input"] += u.input_tokens
        totals["output"] += u.output_tokens
        totals["cache_read"] += getattr(u, "cache_read_input_tokens", 0) or 0
        totals["cache_write"] += getattr(u, "cache_creation_input_tokens", 0) or 0
        working.append({"role": "assistant", "content": resp.content})

        # Server-side web tools can pause when their search/fetch loop hits its limit;
        # re-send (the trailing server_tool_use block tells the API to resume).
        if resp.stop_reason == "pause_turn":
            continue

        if resp.stop_reason != "tool_use":
            final = "".join(b.text for b in resp.content if b.type == "text").strip() or "(no reply)"
            # Persist only the clean user->assistant pair; memory handles the rolling
            # window + summarization of older turns internally.
            memory.record(user_text, final)
            _log_usage(model, totals)
            return final

        # Run every tool Claude asked for, feed the results back, loop again.
        results = []
        for block in resp.content:
            if block.type == "tool_use":
                output = dispatch_tool(block.name, block.input, chat_id)
                results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(output, ensure_ascii=False),
                })
        working.append({"role": "user", "content": results})
