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
    # AI summaries (Phase 10, SPEC Section 15)
    anthropic_api_key: str = field(default="", repr=False)
    ai_summaries_enabled: bool = True
    ai_model: str = "claude-opus-5-5"
    ai_effort: str = "medium"

    @property
    def finnhub_enabled(self) -> bool:
        return bool(self.finnhub_api_key)

    @property
    def ai_enabled(self) -> bool:
        """AI cards show only when switched on AND an Anthropic API key is set."""
        return self.ai_summaries_enabled and bool(self.anthropic_api_key)

    @property
    def sec_user_agent_ok(self) -> bool:
        """SEC asks for a real contact email in the User-Agent."""
        ua = self.sec_user_agent
        return "@" in ua and "YOUR_EMAIL_HERE" not in ua and "example.com" not in ua


def _get(key: str, default: str = "") -> str:
    """Setting from the environment / .env first; when deployed on Streamlit Community Cloud, from the app's
    Secrets (Streamlit only copies Secrets into environment variables after st.secrets is first read)."""
    value = os.getenv(key)
    if value is not None and value.strip() != "":
        return value
    try:
        import streamlit as st
        if key in st.secrets:
            return str(st.secrets[key])
    except Exception:  # noqa: BLE001 - no secrets file (local run) or not running under Streamlit
        pass
    return value if value is not None else default


def load_settings() -> Settings:
    lang = _get("LANGUAGE", "en").strip().lower()
    return Settings(
        sec_user_agent=_get("SEC_USER_AGENT", "").strip(),
        finnhub_api_key=_get("FINNHUB_API_KEY", "").strip(),
        price_provider=_get("PRICE_PROVIDER", "yfinance").strip().lower(),
        production_safe_mode=_bool(_get("PRODUCTION_SAFE_MODE") or None, False),
        language=lang if lang in {"en", "id"} else "en",
        anthropic_api_key=_get("ANTHROPIC_API_KEY", "").strip(),
        ai_summaries_enabled=_bool(_get("AI_SUMMARIES_ENABLED") or None, True),
        ai_model=_get("AI_MODEL", "claude-opus-5-5").strip() or "claude-opus-5-5",
        ai_effort=(_get("AI_EFFORT", "medium").strip().lower() or "medium"),
    )


settings = load_settings()
