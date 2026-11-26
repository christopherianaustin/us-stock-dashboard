"""One AI summary for one tab: cache -> AI -> checks -> one retry -> rule-based fallback (SPEC 15.8, 15.9).

Every AI attempt is logged to logs/ai_summaries.jsonl (input hash, output, checks, model, prompt version, tokens,
cost) so compliance can review samples.
"""
from __future__ import annotations

import json
import threading
from datetime import date, datetime, timezone
from typing import Optional

from config.settings import LOG_DIR, Settings, settings as default_settings
from core.ai_summary import cache
from core.ai_summary.client import AIClient, AIError, AIRefused, Usage, cost_usd, user_message
from core.ai_summary.input_builder import TabInput
from core.ai_summary.validator import validate

LOG_FILE = LOG_DIR / "ai_summaries.jsonl"
FEEDBACK_FILE = LOG_DIR / "ai_feedback.jsonl"
_log_lock = threading.Lock()
_key_locks: dict[str, threading.Lock] = {}   # one generation per cache key at a time (two cards, two tabs...)
# running totals for the debug panel (this process only)
TOTALS = {"calls": 0, "tokens": 0, "cost_usd": 0.0}


def _log(entry: dict, file=None) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with _log_lock, open(file or LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")


VOTES = ("up", "down")


def save_feedback(ticker: str, tab: str, lang: str, prompt_version: str, vote: str, *, source: str = "ai",
                  surface: str = "") -> dict:
    """Thumbs up / down on an AI Insight card (SPEC 15.7), saved to logs/ai_feedback.jsonl."""
    if vote not in VOTES:
        raise ValueError(f"vote must be one of {VOTES}")
    entry = {"time": datetime.now(timezone.utc).isoformat(timespec="seconds"), "ticker": ticker.upper(), "tab": tab,
             "lang": lang, "prompt_version": prompt_version, "vote": vote, "source": source, "surface": surface}
    _log(entry, FEEDBACK_FILE)
    return entry


def fallback_summary(ti: TabInput, lang: str) -> dict:
    """The rule-based strengths (bullish) and risks (bearish) for the tab (Section 7, SPEC 16.6),
    labeled "Automatic summary". Points are plain sentences (no title)."""
    return {
        "label": "Ringkasan otomatis" if lang == "id" else "Automatic summary",
        "bullish": ti.strengths[:4],
        "bearish": ti.risks[:4],
    }


def get_summary(ticker: str, tab: str, lang: str, currency: str, ti: TabInput, *,
                cfg: Optional[Settings] = None, client: Optional[AIClient] = None,
                today: Optional[date] = None, use_cache: bool = True) -> dict:
    """Returns {"enabled", "source": "ai"|"fallback", "summary", "license_tag", "model", "usage", "cost_usd", ...}."""
    cfg = cfg or default_settings
    if not cfg.ai_enabled:
        return {"enabled": False}
    version = cache.prompt_version()
    key = cache.cache_key(ticker, tab, lang, ti.payload, version)
    base = {"enabled": True, "ticker": ticker.upper(), "tab": tab, "lang": lang, "prompt_version": version,
            "license_tag": ti.license_tag, "as_of": ti.payload.get("as_of")}
    if use_cache and (hit := cache.get(key)):
        return {**hit, "cached": True}
    with _log_lock:
        lock = _key_locks.setdefault(key, threading.Lock())
    with lock:   # if the same summary is already being written, wait for it instead of paying twice
        if use_cache and (hit := cache.get(key)):
            return {**hit, "cached": True}
        return _generate(key, base, ticker, tab, lang, currency, ti, cfg, client, today, version)


def _generate(key: str, base: dict, ticker: str, tab: str, lang: str, currency: str, ti: TabInput, cfg: Settings,
              client: Optional[AIClient], today: Optional[date], version: str) -> dict:
    client = client or AIClient(cfg)
    ihash = cache.input_hash(ti.payload)
    total = Usage()
    model_used, note, last_error = cfg.ai_model, None, None
    for attempt in (1, 2):
        msg = user_message(tab, lang, currency, ti.payload, today=today, retry_note=note)
        entry = {"time": datetime.now(timezone.utc).isoformat(timespec="seconds"), "ticker": ticker.upper(),
                 "tab": tab, "lang": lang, "attempt": attempt, "input_hash": ihash, "prompt_version": version,
                 "model_requested": cfg.ai_model, "effort": cfg.ai_effort}
        try:
            r = client.summarize(msg)
        except AIRefused as e:
            _log({**entry, "result": "refused", "error": str(e)})
            last_error = str(e)
            break   # a refusal won't change on retry
        except AIError as e:
            _log({**entry, "result": "error", "error": str(e)})
            last_error = str(e)
            continue
        total = total.add(r.usage)
        model_used = r.model
        check = validate(r.summary, ti.payload, tab, ti.strengths, ti.risks)
        cost = cost_usd(r.usage, r.model)
        TOTALS["calls"] += 1
        TOTALS["tokens"] += r.usage.total
        TOTALS["cost_usd"] = round(TOTALS["cost_usd"] + (cost or 0), 6)
        _log({**entry, "result": "passed" if check.ok else "failed_checks", "model": r.model, "fell_back": r.fell_back,
              "request_id": r.request_id, "checks_failed": check.failures, "usage": r.usage.to_dict(),
              "cost_usd": cost, "output": r.summary.model_dump()})
        if check.ok:
            out = {**base, "source": "ai", "summary": r.summary.model_dump(), "model": r.model,
                   "fell_back_model": r.fell_back, "attempts": attempt, "usage": total.to_dict(),
                   "cost_usd": cost_usd(total, r.model), "cached": False}
            cache.put(key, out)
            return out
        note = "\n".join(f"- {f}" for f in check.failures[:10])
        last_error = "; ".join(check.failures[:3])

    out = {**base, "source": "fallback", "summary": fallback_summary(ti, lang), "model": model_used,
           "usage": total.to_dict(), "cost_usd": cost_usd(total, model_used), "reason": last_error, "cached": False}
    if total.total:   # the AI answered but failed the checks: keep the automatic summary for an hour
        cache.put(key, out, fallback=True)
    return out          # network / API errors are not cached, so the next visit tries again
