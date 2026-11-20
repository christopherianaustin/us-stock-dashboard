"""Earnings analytics (SPEC 6.10): surprises, beat rate, post-earnings price reaction,
estimate revisions, matching announcements to fiscal quarters. Pure functions (no network)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

INLINE_BAND = 1.0   # |surprise| <= 1% counts as "inline"


def surprise_pct(actual, estimate) -> Optional[float]:
    """(actual - estimate) / |estimate| x 100. None if either is missing or the estimate is 0."""
    if actual is None or estimate is None or pd.isna(actual) or pd.isna(estimate) or estimate == 0:
        return None
    return (actual - estimate) / abs(estimate) * 100


def unrounded_estimate(actual, estimate, surprise) -> Optional[float]:
    """Providers round the displayed estimate to cents but compute the surprise from the exact
    estimate (e.g. 0.40 shown, 0.4045 used). Recover it so 'estimate vs actual' matches the surprise.
    Only used when consistent with the rounded value (within half a cent)."""
    if any(v is None or pd.isna(v) for v in (actual, estimate, surprise)):
        return None if estimate is None or pd.isna(estimate) else float(estimate)
    denom = 1 + surprise / 100 if estimate > 0 else 1 - surprise / 100
    if denom == 0:
        return float(estimate)
    exact = actual / denom
    return float(exact) if abs(exact - estimate) <= 0.0051 else float(estimate)


def classify(surprise: Optional[float]) -> Optional[str]:
    """beat / miss / inline (within +/-1%)."""
    if surprise is None or pd.isna(surprise):
        return None
    if surprise > INLINE_BAND:
        return "beat"
    if surprise < -INLINE_BAND:
        return "miss"
    return "inline"


def beat_rate(results: pd.Series, n: int) -> tuple[Optional[float], int, int]:
    """Share of the last n quarters (with a result) that beat estimates -> (rate, beats, counted)."""
    r = results.dropna().tail(n)
    if r.empty:
        return None, 0, 0
    beats = int((r == "beat").sum())
    return beats / len(r), beats, len(r)


@dataclass
class Reaction:
    base_date: Optional[pd.Timestamp]
    reaction_date: Optional[pd.Timestamp]
    move_1d: Optional[float]
    move_5d: Optional[float]


def price_reaction(close: pd.Series, announce_date: pd.Timestamp, timing: str) -> Reaction:
    """Move from the close BEFORE the market could react to the close 1 and 5 trading days after.
       before open -> base = previous day's close, reaction day = announcement day
       after close / unknown -> base = announcement day's close (or last close before), reaction = next day"""
    close = close.dropna()
    d = pd.Timestamp(announce_date).normalize()
    if timing == "before open":
        before = close[close.index < d]
        after = close[close.index >= d]
    else:
        before = close[close.index <= d]
        after = close[close.index > d]
    if before.empty or after.empty:
        return Reaction(None, None, None, None)
    base = float(before.iloc[-1])
    m1 = float(after.iloc[0]) / base - 1
    m5 = float(after.iloc[4]) / base - 1 if len(after) >= 5 else None
    return Reaction(before.index[-1], after.index[0], m1, m5)


def typical_move(moves: pd.Series) -> Optional[float]:
    """Average absolute 1-day move after earnings."""
    m = moves.dropna()
    return float(m.abs().mean()) if len(m) else None


def match_quarter(announce: pd.Timestamp, quarters: pd.DataFrame, max_gap_days: int = 75) -> Optional[dict]:
    """Which fiscal quarter an earnings announcement reports on: the latest quarter that ended
    before the announcement, at most `max_gap_days` earlier. If the company has not filed it with the
    SEC yet (e.g. results announced yesterday), step forward from the last known quarter and mark it estimated.
    quarters: DataFrame with period_end, fiscal_year, fiscal_quarter (sorted)."""
    if quarters is None or quarters.empty:
        return None
    a = pd.Timestamp(announce).normalize()
    before = quarters[quarters["period_end"] < a]
    if before.empty:
        return None
    last = before.iloc[-1]
    gap = (a - last["period_end"]).days
    if gap <= max_gap_days:
        return {"period_end": last["period_end"], "fiscal_year": int(last["fiscal_year"]),
                "fiscal_quarter": int(last["fiscal_quarter"]), "estimated": False}
    fy, fq, pe = int(last["fiscal_year"]), int(last["fiscal_quarter"]), last["period_end"]
    while (a - pe).days > max_gap_days:
        fq, pe = fq + 1, pe + pd.Timedelta(days=91)
        if fq > 4:
            fq, fy = 1, fy + 1
    return {"period_end": pe, "fiscal_year": fy, "fiscal_quarter": fq, "estimated": True}


def revisions_table(eps_trend: Optional[pd.DataFrame]) -> pd.DataFrame:
    """Rows = periods (0q, +1q, 0y, +1y); columns = 90, 60, 30, 7 days ago and now."""
    if eps_trend is None or eps_trend.empty:
        return pd.DataFrame()
    cols = {"90daysAgo": "90 days ago", "60daysAgo": "60 days ago", "30daysAgo": "30 days ago",
            "7daysAgo": "7 days ago", "current": "Now"}
    have = [c for c in cols if c in eps_trend.columns]
    out = eps_trend[have].rename(columns=cols).apply(pd.to_numeric, errors="coerce")
    return out


def revision_direction(row: pd.Series) -> Optional[str]:
    """Up / down / flat: estimate now vs 90 days ago (flat within 1%)."""
    old, now = row.get("90 days ago"), row.get("Now")
    if old is None or now is None or pd.isna(old) or pd.isna(now) or old == 0:
        return None
    ch = now / old - 1
    return "up" if ch > 0.01 else ("down" if ch < -0.01 else "flat")
