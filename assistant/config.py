"""Central config. Loads from .env so secrets never live in code."""
import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()  # reads .env in the repo root if present

REPO_ROOT = Path(__file__).resolve().parent.parent


def _require(name: str) -> str:
    val = os.getenv(name)
    if not val:
        raise RuntimeError(f"Missing required env var: {name} (see .env.example)")
    return val


@dataclass(frozen=True)
class Settings:
    anthropic_api_key: str
    telegram_bot_token: str
    allowed_telegram_user_id: int
    model_reasoning: str
    model_routing: str
    data_dir: Path
    database_url: str
    openai_api_key: str  # embeddings only; optional so the Phase 0 bot still runs without it


# Default the connection string from the docker-compose creds so there's nothing
# extra to set locally. Override DATABASE_URL in .env for a remote/VPS Postgres later.
_DEFAULT_DB_URL = (
    f"postgresql://assistant:{os.getenv('POSTGRES_PASSWORD', 'localdev')}"
    "@localhost:5432/assistant"
)

settings = Settings(
    anthropic_api_key=_require("ANTHROPIC_API_KEY"),
    telegram_bot_token=_require("TELEGRAM_BOT_TOKEN"),
    # int() so we compare against Telegram's numeric from_id directly
    allowed_telegram_user_id=int(_require("ALLOWED_TELEGRAM_USER_ID")),
    model_reasoning=os.getenv("MODEL_REASONING", "claude-sonnet-4-6"),
    model_routing=os.getenv("MODEL_ROUTING", "claude-haiku-4-5-20251001"),
    data_dir=REPO_ROOT / "data",
    database_url=os.getenv("DATABASE_URL", _DEFAULT_DB_URL),
    openai_api_key=os.getenv("OPENAI_API_KEY", ""),  # blank is OK until embeddings are used
)
