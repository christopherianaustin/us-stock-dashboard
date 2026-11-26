"""Safety and accuracy checks run on every AI summary before it is shown (SPEC 15.8).

1. Banned phrases (our own buy/sell/hold calls, predictions, promises), in English and Indonesian.
   Exception: sentences that clearly attribute the words to analysts, in the tabs listed in the config.
2. Number check: every number in the output must be in the input data (within rounding).
3. Length check: the limits in schema.LIMITS.
4. Signal check: moves at most one step from the rule-based signal.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Iterable

import yaml

from config.settings import CONFIG_DIR
from core.ai_summary.schema import LIMITS, TabSummary

# numbers like 12, 12.5, 12,5, 1,234,567.8, 1.234.567,8
NUM_RE = re.compile(r"\d+(?:[.,]\d+)*")
# numbers that may appear without being in the data ("for every $100", "one of 1")
ALWAYS_OK = {0.0, 1.0, 100.0}
SIGNAL_ORDER = {"Weak": 0, "Neutral": 1, "Strong": 2}


@dataclass
class CheckResult:
    ok: bool
    failures: list[str] = field(default_factory=list)


@lru_cache(maxsize=1)
def banned_config() -> dict:
    with open(CONFIG_DIR / "ai_banned_phrases.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


# =========================================================================== text helpers
def texts_of(s: TabSummary) -> list[tuple[str, str]]:
    """(field name, text) for every piece of text in a summary."""
    out = [("headline", s.headline), ("takeaway", s.takeaway), ("ask_yourself", s.ask_yourself)]
    out += [(f"positives[{i}]", p.text) for i, p in enumerate(s.positives)]
    out += [(f"watch_outs[{i}]", p.text) for i, p in enumerate(s.watch_outs)]
    out += [(f"what_to_watch_next[{i}]", t) for i, t in enumerate(s.what_to_watch_next)]
    out += [(f"data_gaps[{i}]", t) for i, t in enumerate(s.data_gaps)]
    return out


def sentences(text: str) -> list[str]:
    # split after . ! ? when followed by a space; keeps decimals like 12.5 together
    return [x for x in re.split(r"(?<=[.!?])\s+", text.strip()) if x]


def words(text: str) -> int:
    return len(text.split())


def _phrase_re(phrase: str) -> re.Pattern:
    p = re.escape(phrase.lower()).replace("\\ ", r"\s+").replace("'", "['’]")
    return re.compile(rf"(?<![\w-]){p}(?![\w-])", re.IGNORECASE)


# =========================================================================== 1. banned phrases
def check_banned(s: TabSummary, tab: str) -> list[str]:
    cfg = banned_config()
    phrases = list(cfg.get("en", [])) + list(cfg.get("id", []))
    exempt_tab = tab in cfg.get("analyst_exception_tabs", [])
    analyst_res = [_phrase_re(w) for w in cfg.get("analyst_words", [])]
    failures = []
    for name, text in texts_of(s):
        for sent in sentences(text):
            if exempt_tab and any(r.search(sent) for r in analyst_res):
                continue
            for ph in phrases:
                if _phrase_re(ph).search(sent):
                    failures.append(f'banned phrase "{ph}" in {name}: "{sent}"')
    return failures


# =========================================================================== 2. numbers
def _readings(token: str) -> set[float]:
    """Every sensible reading of a number written in English (1,234.5) or Indonesian (1.234,5) style."""
    out: set[float] = set()
    for thousands, decimal in ((",", "."), (".", ",")):
        t = token
        parts = t.split(decimal)
        if len(parts) > 2:
            continue
        whole = parts[0].replace(thousands, "")
        if not whole.isdigit():
            continue
        if thousands in parts[0] and not re.fullmatch(rf"\d{{1,3}}(?:\{thousands}\d{{3}})+", parts[0]):
            continue
        txt = whole + ("." + parts[1] if len(parts) == 2 else "")
        try:
            out.add(float(txt))
        except ValueError:
            pass
    return out


def numbers_in_text(text: str) -> list[tuple[str, set[float]]]:
    return [(m.group(0), _readings(m.group(0))) for m in NUM_RE.finditer(text)]


def numbers_in_data(data: Any) -> set[float]:
    """Every number in the input JSON: values, and numbers inside strings and keys (dates, labels, insights)."""
    found: set[float] = set()

    def walk(x: Any) -> None:
        if isinstance(x, bool) or x is None:
            return
        if isinstance(x, (int, float)):
            found.add(abs(float(x)))
        elif isinstance(x, str):
            for _, rs in numbers_in_text(x):
                found.update(rs)
        elif isinstance(x, dict):
            for k, v in x.items():
                walk(str(k))
                walk(v)
        elif isinstance(x, (list, tuple)):
            for v in x:
                walk(v)

    walk(data)
    return found


def matches(out: float, data: Iterable[float]) -> bool:
    """Within 1%, or the same value written with fewer decimals (15.27 -> 15.3 or 15)."""
    if out in ALWAYS_OK:
        return True
    if out.is_integer() and 1900 <= out <= 2100:      # a year must match exactly (2027 is not "within 1%" of 2028)
        return out in data
    for d in data:
        if d == out:
            return True
        if d and abs(out - d) / abs(d) <= 0.01:
            return True
        if any(round(d, n) == out for n in range(0, 3)):
            return True
    return False


def check_numbers(s: TabSummary, payload: dict) -> list[str]:
    data = numbers_in_data(payload)
    failures = []
    for name, text in texts_of(s):
        for token, readings in numbers_in_text(text):
            if readings and not any(matches(r, data) for r in readings):
                failures.append(f'number "{token}" in {name} is not in the data')
    return failures


# =========================================================================== 3. lengths, 4. signal
def check_lengths(s: TabSummary) -> list[str]:
    L, f = LIMITS, []
    if words(s.headline) > L["headline_words"]:
        f.append(f'headline has {words(s.headline)} words (max {L["headline_words"]})')
    if words(s.takeaway) > L["takeaway_words"]:
        f.append(f'takeaway has {words(s.takeaway)} words (max {L["takeaway_words"]})')
    if len(sentences(s.takeaway)) > L["takeaway_sentences"]:
        f.append(f'takeaway has {len(sentences(s.takeaway))} sentences (max {L["takeaway_sentences"]})')
    for kind in ("positives", "watch_outs"):
        pts = getattr(s, kind)
        if len(pts) > L["points"]:
            f.append(f"{kind} has {len(pts)} points (max {L['points']})")
        for i, p in enumerate(pts):
            if words(p.text) > L["point_words"]:
                f.append(f"{kind}[{i}] has {words(p.text)} words (max {L['point_words']})")
    if len(s.what_to_watch_next) > L["what_to_watch_next"]:
        f.append(f"what_to_watch_next has {len(s.what_to_watch_next)} items (max {L['what_to_watch_next']})")
    if not s.headline.strip() or not s.takeaway.strip():
        f.append("headline or takeaway is empty")
    if s.ask_yourself.count("?") != 1:
        f.append("ask_yourself must be exactly one question")
    return f


def check_signal(s: TabSummary, rule_signal: str) -> list[str]:
    a, b = SIGNAL_ORDER.get(rule_signal), SIGNAL_ORDER.get(s.signal)
    if rule_signal == "Not applicable" and s.signal != "Not applicable":
        return [f'signal must stay "Not applicable" for this tab (got "{s.signal}")']
    if a is not None and b is not None and abs(a - b) > 1:
        return [f'signal moved more than one step ("{rule_signal}" -> "{s.signal}")']
    return []


# =========================================================================== all checks
def validate(s: TabSummary, payload: dict, tab: str, rule_signal: str) -> CheckResult:
    failures = check_lengths(s) + check_signal(s, rule_signal) + check_banned(s, tab) + check_numbers(s, payload)
    return CheckResult(ok=not failures, failures=failures)


def payload_hash_text(payload: dict) -> str:
    """Stable JSON text of the input (sorted keys), used for hashing and for the prompt."""
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
