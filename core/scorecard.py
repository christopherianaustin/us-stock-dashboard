"""Scorecard: 7 pillar scores (0-100) and plain-language strengths / risks (SPEC Section 7).

Thresholds live in config/scoring.yaml and texts in config/insights_<lang>.yaml, so the team
can tune them without coding. Our own wording is "Strong / Neutral / Weak" - never buy / sell.
"""
from __future__ import annotations

import functools
import math
from dataclasses import dataclass, field
from typing import Any, Optional

import pandas as pd
import yaml

from config.settings import CONFIG_DIR

PILLARS = ["valuation", "growth", "profitability", "financial_health", "earnings_quality", "momentum", "dividend"]

# Facts that come from (or use) demo-only sources: dropped in production-safe mode
DEMO_FACTS = {"pe_vs_history", "pe_vs_peers", "ev_ebitda_vs_peers", "fcf_yield", "peg", "forward_growth", "altman_z",
              "beat_rate_8", "beats_8", "quarters_8", "estimate_change_90d", "vs_sma50", "vs_sma200", "rel_strength_6m",
              "from_52w_high", "yield_vs_5y_avg", "growth_streak", "pe_percentile", "volatility", "current_drawdown",
              "short_pct"}


@functools.lru_cache(maxsize=1)
def scoring_config() -> dict:
    with open(CONFIG_DIR / "scoring.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


@functools.lru_cache(maxsize=4)
def insight_texts(lang: str = "en") -> dict:
    path = CONFIG_DIR / f"insights_{lang}.yaml"
    if not path.exists():
        path = CONFIG_DIR / "insights_en.yaml"
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


# =========================================================================== facts
def _num(v) -> Optional[float]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) or math.isinf(f) else f


def _dp(snapshot: dict, key: str) -> Optional[float]:
    dp = snapshot.get(key)
    return _num(dp.value) if dp is not None and dp.available else None


def _ratio(a, b) -> Optional[float]:
    a, b = _num(a), _num(b)
    return a / b if a is not None and b not in (None, 0) and b > 0 else None


def build_facts(analysis=None, price=None, earnings=None, dividends=None, ownership=None) -> dict[str, float]:
    """Flatten everything the scorecard needs into {fact name: number}. Missing inputs are simply absent."""
    f: dict[str, Any] = {}
    if analysis is not None:
        s = analysis.snapshot
        for k in ("fcf_yield", "peg", "revenue_yoy", "eps_yoy", "revenue_cagr_3y", "net_margin", "roe", "roic",
                  "debt_to_equity", "current_ratio", "interest_coverage", "cash_conversion", "net_debt"):
            f[k] = _dp(s, k)
        pe = _dp(s, "pe")
        st_pe = analysis.stats.get("pe")
        if pe is not None and st_pe is not None:
            f["pe_vs_history"] = _ratio(pe, st_pe.median)
            f["pe_percentile"] = st_pe.percentile
        f["pe_vs_peers"] = _ratio(pe, analysis.peer_medians.get("pe"))
        f["ev_ebitda_vs_peers"] = _ratio(_dp(s, "ev_ebitda"), analysis.peer_medians.get("ev_ebitda"))
        f["forward_growth"] = analysis.estimates.growth
        q = analysis.quarterly
        if q is not None and not q.empty:
            nm = q["net_margin_ttm"].dropna()
            if len(nm) >= 5:
                f["net_margin_change"] = float(nm.iloc[-1] - nm.iloc[-5])
            ni = q["net_income_ttm"].dropna()
            if len(ni):
                f["net_income_ttm"] = float(ni.iloc[-1])
            eb = q["ebitda_ttm"].dropna()
            if f.get("net_debt") is not None and len(eb) and eb.iloc[-1] > 0:
                f["net_debt_to_ebitda"] = f["net_debt"] / float(eb.iloc[-1])
        if analysis.altman.z is not None:
            f["altman_z"] = analysis.altman.z
        p = analysis.piotroski
        if p.tested >= 5:
            f["piotroski"] = p.score * 9 / p.tested          # scaled when some tests can't be run
            if p.tested == 9:
                f["piotroski_score"] = p.score
    if price is not None:
        sn = price.snap
        f["vs_sma50"] = _ratio(sn.price, sn.sma50) - 1 if _ratio(sn.price, sn.sma50) else None
        f["vs_sma200"] = _ratio(sn.price, sn.sma200) - 1 if _ratio(sn.price, sn.sma200) else None
        f["from_52w_high"] = sn.from_high_52w
        r = price.returns
        if "6M" in r.index and price.symbol in r.columns and "SPY" in r.columns:
            a, b = _num(r.loc["6M", price.symbol]), _num(r.loc["6M", "SPY"])
            f["rel_strength_6m"] = a - b if a is not None and b is not None else None
        f["volatility"] = price.risk.volatility_1y
        f["current_drawdown"] = price.risk.current_drawdown
    if earnings is not None:
        rate, beats, n = earnings.beat_rate_8
        if n:
            f["beat_rate_8"], f["beats_8"], f["quarters_8"] = rate, beats, n
        rv = earnings.revisions
        if not rv.empty and "Next fiscal year" in rv.index:
            row = rv.loc["Next fiscal year"]
            f["estimate_change_90d"] = _ratio(row.get("Now"), row.get("90 days ago"))
            if f["estimate_change_90d"] is not None:
                f["estimate_change_90d"] -= 1
    if dividends is not None and dividends.summary.pays:
        sm = dividends.summary
        f["yield_vs_5y_avg"] = _ratio(sm.yield_ttm, sm.yield_5y_avg)
        f["payout_ratio"] = dividends.payout_ratio
        f["growth_streak"] = sm.streak
        f["pays_dividend"] = 1.0
    elif dividends is not None:
        f["pays_dividend"] = 0.0
    if ownership is not None:
        f["short_pct"] = ownership.short.get("pct_float")
    f["debt_to_equity_or_zero"] = f.get("debt_to_equity") or 0.0
    return {k: v for k, v in ((k, _num(v)) for k, v in f.items()) if v is not None}


def facts_for_mode(facts: dict[str, float], safe_mode: bool) -> dict[str, float]:
    return {k: v for k, v in facts.items() if not (safe_mode and k in DEMO_FACTS)}


# =========================================================================== scoring
def score_metric(value: float, rule: str, rng: list[float]) -> float:
    """0-100 on a straight line between the 'bad' and 'good' thresholds."""
    if rule == "higher_better":
        bad, good = rng
    else:
        good, bad = rng
    if good == bad:
        return 100.0 if (value >= good if rule == "higher_better" else value <= good) else 0.0
    t = (value - bad) / (good - bad)
    return round(100 * min(max(t, 0.0), 1.0), 1)


def level_for(score: Optional[float]) -> Optional[str]:
    if score is None:
        return None
    lv = scoring_config()["levels"]
    return "strong" if score >= lv["strong"] else ("neutral" if score >= lv["neutral"] else "weak")


@dataclass
class PillarScore:
    pillar: str
    score: Optional[float]
    level: Optional[str]          # strong / neutral / weak / None (not enough data) / "not_applicable"
    used: int
    total: int
    details: list[dict] = field(default_factory=list)


def score_pillars(facts: dict[str, float]) -> dict[str, PillarScore]:
    cfg = scoring_config()["pillars"]
    out = {}
    for pillar in PILLARS:
        metrics = cfg[pillar]["metrics"]
        if pillar == "dividend" and facts.get("pays_dividend") == 0.0:
            out[pillar] = PillarScore(pillar, None, "not_applicable", 0, len(metrics))
            continue
        details, wsum, total_w = [], 0.0, 0.0
        for name, m in metrics.items():
            v = facts.get(name)
            if v is None:
                details.append({"metric": name, "value": None, "points": None})
                continue
            pts = score_metric(v, m["rule"], m["range"])
            details.append({"metric": name, "value": v, "points": pts})
            wsum += pts * m.get("weight", 1)
            total_w += m.get("weight", 1)
        used = sum(d["points"] is not None for d in details)
        # need at least 2 metrics (or all, if the pillar has fewer) for a meaningful score
        if used == 0 or used < min(2, len(metrics)):
            out[pillar] = PillarScore(pillar, None, None, used, len(metrics), details)
        else:
            sc = round(wsum / total_w, 0)
            out[pillar] = PillarScore(pillar, sc, level_for(sc), used, len(metrics), details)
    return out


# =========================================================================== insights
@dataclass
class Insight:
    id: str
    kind: str        # strength / risk
    pillar: str
    priority: int
    text: str


def _pct(v: float) -> str:
    a = abs(v) * 100
    return f"{v * 100:.1f}%" if a < 10 else f"{v * 100:.0f}%"


def _money(v: float) -> str:
    a = abs(v)
    for div, suf in ((1e12, "T"), (1e9, "B"), (1e6, "M")):
        if a >= div:
            return f"{'-' if v < 0 else ''}${a / div:,.1f}{suf}"
    return f"{'-' if v < 0 else ''}${a:,.0f}"


def format_values(facts: dict[str, float]) -> dict[str, str]:
    """All the placeholder variants the templates can use."""
    out: dict[str, str] = {}
    for k, v in facts.items():
        out[f"{k}_pct"] = _pct(v)
        out[f"{k}_abs_pct"] = _pct(abs(v))
        out[f"{k}_x"] = f"{v:.1f}×"
        out[f"{k}_money"] = _money(v)
        out[f"{k}_num"] = f"{v:.2f}"
        out[k] = f"{v:.0f}" if float(v).is_integer() else f"{v:.2f}"
    if "net_debt" in facts:
        out["net_cash_money"] = _money(-facts["net_debt"])
    if "pe_percentile" in facts:
        out["pe_percentile_low_pct"] = _pct(1 - facts["pe_percentile"])
    if "pe_vs_peers" in facts:
        out["pe_vs_peers_discount_pct"] = _pct(1 - facts["pe_vs_peers"])
        out["pe_vs_peers_premium_pct"] = _pct(facts["pe_vs_peers"] - 1)
    for k in ("beats_8", "quarters_8", "growth_streak", "piotroski_score"):
        if k in facts:
            out[k] = f"{int(facts[k])}"
    return out


OPS = {">": lambda a, b: a > b, ">=": lambda a, b: a >= b, "<": lambda a, b: a < b, "<=": lambda a, b: a <= b,
       "==": lambda a, b: a == b}


def _matches(rule: dict, facts: dict[str, float]) -> bool:
    for name, op, value in rule["when"]:
        v = facts.get(name)
        if v is None or not OPS[op](v, value):
            return False
    return True


def generate_insights(facts: dict[str, float], lang: str = "en", limit: int = 5,
                      skip_pillars: tuple[str, ...] = ()) -> tuple[list[Insight], list[Insight]]:
    cfg, texts = scoring_config(), insight_texts(lang)
    values = format_values(facts)
    result = {}
    for kind, key in (("strength", "strengths"), ("risk", "risks")):
        found = []
        for rule in cfg[key]:
            if rule["pillar"] in skip_pillars or not _matches(rule, facts):
                continue
            template = texts[key].get(rule["id"])
            if not template:
                continue
            try:
                text = template.format(**values)
            except (KeyError, IndexError, ValueError):
                continue   # a needed value is missing -> skip rather than show a broken sentence
            found.append(Insight(rule["id"], kind, rule["pillar"], rule["priority"], text))
        found.sort(key=lambda i: -i.priority)
        result[kind] = found[:limit]
    return result["strength"], result["risk"]


@dataclass
class Scorecard:
    pillars: dict[str, PillarScore]
    strengths: list[Insight]
    risks: list[Insight]
    facts: dict[str, float]


def build_scorecard(facts: dict[str, float], lang: str = "en", safe_mode: bool = False) -> Scorecard:
    f = facts_for_mode(facts, safe_mode)
    pillars = score_pillars(f)
    skip = ("dividend",) if pillars["dividend"].level == "not_applicable" else ()
    strengths, risks = generate_insights(f, lang, skip_pillars=skip)
    return Scorecard(pillars=pillars, strengths=strengths, risks=risks, facts=f)
