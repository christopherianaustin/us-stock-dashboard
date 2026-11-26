"""Result cache for AI summaries (SPEC 15.9).

Key = ticker + tab + language + PROMPT_VERSION + hash of the input JSON, so a summary is reused for 24 hours
or until the data it was written from changes (a new price, a new quarter...), whichever comes first.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Optional

import diskcache

from config.settings import CACHE_DIR

TTL_SECONDS = 24 * 3600
FALLBACK_TTL_SECONDS = 3600          # an automatic (rule-based) summary is retried with AI after an hour
VOLATILE_KEYS = ("as_of",)           # time stamps that change on every request but not the data itself

_cache: Optional[diskcache.Cache] = None


def prompt_version() -> str:
    return (Path(__file__).parent / "PROMPT_VERSION").read_text(encoding="utf-8").strip()


def input_hash(payload: dict) -> str:
    stable = {k: v for k, v in payload.items() if k not in VOLATILE_KEYS}
    text = json.dumps(stable, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def cache_key(ticker: str, tab: str, lang: str, payload: dict, version: Optional[str] = None) -> str:
    return f"ai|{ticker.upper()}|{tab}|{lang}|v{version or prompt_version()}|{input_hash(payload)}"


def _store() -> diskcache.Cache:
    global _cache
    if _cache is None:
        _cache = diskcache.Cache(str(CACHE_DIR / "ai_summary"))
    return _cache


def get(key: str) -> Optional[dict]:
    return _store().get(key)


def put(key: str, value: dict[str, Any], fallback: bool = False) -> None:
    _store().set(key, value, expire=FALLBACK_TTL_SECONDS if fallback else TTL_SECONDS)
