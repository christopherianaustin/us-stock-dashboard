"""Safety and accuracy checks run on every AI summary before it is shown (SPEC 15.8, as changed by 16.6).

1. Banned phrases (our own buy/sell/hold calls, predictions, promises), in English and Indonesian.
   Exception: sentences that clearly attribute the words to analysts, in the tabs listed in the config.
2. Number check: every number in the output must be in the input data (within rounding).
3. Length check: the limits in schema.LIMITS (0-4 points per list, title 2-6 words, detail max 25 words,
   data_gaps max 3).
4. Completeness: not too thin for the amount of data, and no empty side when our rule-based checks found
   strengths or risks for this tab.
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
    out = []
    for kind in ("bullish", "bearish"):
        for i, p in enumerate(getattr(s, kind)):
            out += [(f"{kind}[{i}].title", p.title), (f"{kind}[{i}].detail", p.detail)]
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
    allowed_res = [_phrase_re(w) for w in cfg.get("allowed_phrases", [])]
    failures = []
    for name, text in texts_of(s):
        for sent in sentences(text):
            for r in allowed_res:
                sent = r.sub(" ", sent)
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


NAMED_NUMBERS = re.compile(r"S&P\s?500", re.IGNORECASE)    # index names, not data ("S&P 500")


def check_numbers(s: TabSummary, payload: dict) -> list[str]:
    data = numbers_in_data(payload)
    failures = []
    for name, text in texts_of(s):
        for token, readings in numbers_in_text(NAMED_NUMBERS.sub("S&P", text)):
            if readings and not any(matches(r, data) for r in readings):
                failures.append(f'number "{token}" in {name} is not in the data')
    return failures


# =========================================================================== 3. lengths
def check_lengths(s: TabSummary) -> list[str]:
    L, f = LIMITS, []
    for kind in ("bullish", "bearish"):
        pts = getattr(s, kind)
        if len(pts) > L["points"]:
            f.append(f"{kind} has {len(pts)} points (max {L['points']})")
        for i, p in enumerate(pts):
            n = words(p.title)
            if not L["title_words_min"] <= n <= L["title_words_max"]:
                f.append(f"{kind}[{i}].title has {n} words ({L['title_words_min']} to {L['title_words_max']})")
            if words(p.detail) > L["detail_words"]:
                f.append(f"{kind}[{i}].detail has {words(p.detail)} words (max {L['detail_words']})")
            if len(sentences(p.detail)) > 1:
                f.append(f"{kind}[{i}].detail has {len(sentences(p.detail))} sentences (must be one)")
    if len(s.data_gaps) > L["data_gaps"]:
        f.append(f"data_gaps has {len(s.data_gaps)} items (max {L['data_gaps']})")
    return f


# =========================================================================== 4. completeness
THIN_POINTS = 1          # a card with this many points or fewer ...
RICH_DATA = 10           # ... is too thin when the tab has at least this many facts


def data_facts(payload: dict) -> int:
    """Rough count of facts in a tab's input: numbers, headlines and a long company description."""
    def walk(x) -> int:
        if isinstance(x, bool) or x is None:
            return 0
        if isinstance(x, (int, float)):
            return 1
        if isinstance(x, str):
            return 10 if len(x) > 300 else 0       # e.g. the company description
        if isinstance(x, dict):
            return sum(walk(v) for k, v in x.items() if k not in ("rule_based_pillars", "as_of"))
        if isinstance(x, list):
            return sum(walk(v) if not (isinstance(v, dict) and "headline" in v) else 1 for v in x)
        return 0
    return walk(payload)


def check_completeness(s: TabSummary, payload: dict, strengths=(), risks=()) -> list[str]:
    """Catch answers that leave out most of the tab (SPEC 16.1: short, but complete)."""
    f = []
    n = len(s.bullish) + len(s.bearish)
    if n <= THIN_POINTS and data_facts(payload) >= RICH_DATA:
        f.append(f"only {n} point(s) for a tab with a lot of data: go through every metric, comparison and "
                 "headline, and cover each important one (most tabs need 2 to 4 points per side)")
    if strengths and not s.bullish:
        f.append(f'bullish is empty, but the data shows strengths, for example: "{strengths[0]}"')
    if risks and not s.bearish:
        f.append(f'bearish is empty, but the data shows risks, for example: "{risks[0]}"')
    return f


# =========================================================================== all checks
def validate(s: TabSummary, payload: dict, tab: str, strengths=(), risks=()) -> CheckResult:
    failures = (check_lengths(s) + check_banned(s, tab) + check_numbers(s, payload)
                + check_completeness(s, payload, strengths, risks))
    return CheckResult(ok=not failures, failures=failures)


def payload_hash_text(payload: dict) -> str:
    """Stable JSON text of the input (sorted keys), used for hashing and for the prompt."""
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
