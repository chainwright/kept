"""Runtime settings, read once from the environment (and an optional .env file)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # dotenv is optional
    pass

ROOT = Path(__file__).resolve().parent.parent


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


@dataclass(frozen=True)
class Tier:
    """One Nemotron size class and why we reach for it."""

    name: str
    model_hint: str          # substring used to find the model id in /v1/models
    default_model: str       # used if /v1/models is unreachable
    usd_in_per_m: float      # list price per 1M input tokens (approximate, shown in the UI)
    usd_out_per_m: float
    why: str


TIERS = {
    "nano": Tier("nano", "nano", "nvidia/Nemotron-3-Nano-30B-A3B", 0.06, 0.24,
                 "cheap and fast: sorting, tagging, yes/no questions"),
    "super": Tier("super", "super", "nvidia/Nemotron-3-Super-120B-A12B", 0.30, 0.90,
                  "planning the day and drafting text that someone will read"),
    "ultra": Tier("ultra", "ultra", "nvidia/Nemotron-3-Ultra-550b-a55b", 1.00, 3.00,
                  "the one hard judgement call where a mistake costs real money"),
}


@dataclass
class Settings:
    nebius_api_key: str = field(default_factory=lambda: _env("NEBIUS_API_KEY"))
    nebius_base_url: str = field(default_factory=lambda: _env(
        "NEBIUS_BASE_URL", "https://api.tokenfactory.nebius.com/v1/"))
    tavily_api_key: str = field(default_factory=lambda: _env("TAVILY_API_KEY"))
    telegram_bot_token: str = field(default_factory=lambda: _env("TELEGRAM_BOT_TOKEN"))
    telegram_chat_id: str = field(default_factory=lambda: _env("TELEGRAM_CHAT_ID"))
    data_dir: Path = field(default_factory=lambda: Path(_env("KEPT_DATA_DIR", str(ROOT / "data"))))
    owner_name: str = field(default_factory=lambda: _env("KEPT_OWNER_NAME", "Alex"))
    timezone: str = field(default_factory=lambda: _env("KEPT_TZ", "America/Los_Angeles"))
    # demo mode: outgoing mail lands in data/outbox instead of a real SMTP server,
    # so anyone (including judges) can press "Yes" without emailing a stranger
    demo: bool = field(default_factory=lambda: _env("KEPT_DEMO", "1") == "1")
    daily_budget_usd: float = field(default_factory=lambda: float(_env("KEPT_DAILY_BUDGET_USD", "1.00")))
    smtp_host: str = field(default_factory=lambda: _env("SMTP_HOST"))
    smtp_user: str = field(default_factory=lambda: _env("SMTP_USER"))
    smtp_password: str = field(default_factory=lambda: _env("SMTP_PASSWORD"))

    def model_override(self, tier: str) -> str:
        return _env(f"KEPT_MODEL_{tier.upper()}")


settings = Settings()
