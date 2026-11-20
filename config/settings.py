"""App settings: read from environment variables / the .env file.

Everything configurable lives here so no secret is ever hardcoded.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"
CACHE_DIR = PROJECT_ROOT / ".cache"
LOG_DIR = PROJECT_ROOT / "logs"

load_dotenv(PROJECT_ROOT / ".env")


def _bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


# Cache time-to-live in seconds (Section 10 of SPEC.md)
CACHE_TTL = {
    "price_history": 15 * 60,
    "quote": 60,
    "sec_companyfacts": 24 * 3600,
    "sec_submissions": 6 * 3600,
    "estimates": 6 * 3600,
    "statements": 24 * 3600,
    "news": 30 * 60,
    "profile": 7 * 24 * 3600,
    "sec_tickers": 7 * 24 * 3600,
}


@dataclass
class Settings:
    sec_user_agent: str = ""
    finnhub_api_key: str = ""
    price_provider: str = "yfinance"
    production_safe_mode: bool = False
    language: str = "en"
    cache_ttl: dict = field(default_factory=lambda: dict(CACHE_TTL))

    @property
    def finnhub_enabled(self) -> bool:
        return bool(self.finnhub_api_key)

    @property
    def sec_user_agent_ok(self) -> bool:
        """SEC asks for a real contact email in the User-Agent."""
        ua = self.sec_user_agent
        return "@" in ua and "YOUR_EMAIL_HERE" not in ua and "example.com" not in ua


def load_settings() -> Settings:
    lang = os.getenv("LANGUAGE", "en").strip().lower()
    return Settings(
        sec_user_agent=os.getenv("SEC_USER_AGENT", "").strip(),
        finnhub_api_key=os.getenv("FINNHUB_API_KEY", "").strip(),
        price_provider=os.getenv("PRICE_PROVIDER", "yfinance").strip().lower(),
        production_safe_mode=_bool(os.getenv("PRODUCTION_SAFE_MODE"), False),
        language=lang if lang in {"en", "id"} else "en",
    )


settings = load_settings()
