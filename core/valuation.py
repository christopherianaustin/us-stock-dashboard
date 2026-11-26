"""Valuation history, history statistics, DCF and peer comparison (SPEC 6.4).

Valuation history avoids look-ahead bias: on each trading day we only use financial
data whose filing date (when it became public) is on or before that day.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd


# =========================================================================== history
def valuation_history(q: pd.DataFrame, close: pd.Series, is_financial: bool = False) -> pd.DataFrame:
    """Daily P/E, P/S and EV/EBITDA using TTM values known on each day.

    q:     quarterly_metrics() table (needs known_date, eps_diluted_ttm, revenue_ttm, ebitda_ttm,
           net_income_ttm, net_debt, shares)
    close: daily closing prices (split-adjusted), DatetimeIndex
    """
    if q.empty or close is None or close.empty or "known_date" not in q:
        return pd.DataFrame()
    cols = ["known_date", "eps_diluted_ttm", "revenue_ttm", "ebitda_ttm", "net_income_ttm", "net_debt", "shares"]
    fund = q[cols].dropna(subset=["known_date"]).sort_values("known_date")
    if fund.empty:
        return pd.DataFrame()
    px = close.copy()
    px.index = pd.DatetimeIndex(px.index).tz_localize(None).normalize()
    px = px.to_frame("close").reset_index(names="date").sort_values("date")
    fund = fund.assign(known_date=pd.to_datetime(fund["known_date"]).astype("datetime64[ns]"))
    px["date"] = px["date"].astype("datetime64[ns]")
    df = pd.merge_asof(px, fund, left_on="date", right_on="known_date", direction="backward").set_index("date")

    mcap = df["close"] * df["shares"]
    eps = df["eps_diluted_ttm"]
    pe_eps = df["close"] / eps.where(eps > 0)
    pe_ni = mcap / df["net_income_ttm"].where(df["net_income_ttm"] > 0)
    out = pd.DataFrame(index=df.index)
    out["close"] = df["close"]
    out["pe"] = pe_eps.where(eps.notna(), pe_ni)       # fall back to mcap / net income if no EPS
    out["ps"] = mcap / df["revenue_ttm"].where(df["revenue_ttm"] > 0)
    if not is_financial:
        ev = mcap + df["net_debt"].fillna(0)
        out["ev_ebitda"] = ev / df["ebitda_ttm"].where(df["ebitda_ttm"] > 0)
    else:
        out["ev_ebitda"] = np.nan
    return out


@dataclass
class HistoryStats:
    current: Optional[float]
    median: Optional[float]
    low: Optional[float]
    high: Optional[float]
    std: Optional[float]
    percentile: Optional[float]   # share of history days with a LOWER value than today (0..1)
    days: int


def history_stats(series: pd.Series, current: Optional[float] = None) -> HistoryStats:
    s = series.replace([np.inf, -np.inf], np.nan).dropna()
    if s.empty:
        return HistoryStats(current, None, None, None, None, None, 0)
    cur = current if current is not None else float(s.iloc[-1])
    return HistoryStats(current=cur, median=float(s.median()), low=float(s.min()), high=float(s.max()),
                        std=float(s.std()) if len(s) > 1 else 0.0,
                        percentile=float((s < cur).mean()), days=int(len(s)))


def percentile_sentence(name: str, st: HistoryStats) -> Optional[str]:
    if st.percentile is None or st.current is None:
        return None
    p = round(st.percentile * 100)
    if p >= 50:
        return f"{name} is higher than {p}% of the last 5 years, so the price is higher than usual for what you get."
    return f"{name} is lower than {100 - p}% of the last 5 years, so the price is lower than usual for what you get."


# =========================================================================== DCF
@dataclass
class DCFResult:
    per_share: Optional[float]
    enterprise_value: Optional[float]
    equity_value: Optional[float]
    pv_fcf: list[float] = field(default_factory=list)
    pv_terminal: Optional[float] = None
    projected_fcf: list[float] = field(default_factory=list)
    reason: Optional[str] = None


def dcf(fcf0: Optional[float], growth: float, discount: float, terminal_growth: float,
        net_debt: Optional[float], shares: Optional[float], years: int = 5) -> DCFResult:
    """Simple 5-year DCF:
       FCF_t = FCF0 x (1+g)^t, terminal value = FCF_5 x (1+tg) / (r - tg),
       fair value per share = (PV of FCFs + PV of terminal value - net debt) / shares."""
    if fcf0 is None or (isinstance(fcf0, float) and math.isnan(fcf0)):
        return DCFResult(None, None, None, reason="Needs free cash flow")
    if fcf0 <= 0:
        return DCFResult(None, None, None, reason="A DCF needs positive free cash flow")
    if not shares or shares <= 0:
        return DCFResult(None, None, None, reason="Needs the number of shares")
    if discount <= terminal_growth:
        return DCFResult(None, None, None, reason="Discount rate must be higher than terminal growth")
    projected = [fcf0 * (1 + growth) ** t for t in range(1, years + 1)]
    pv = [f / (1 + discount) ** t for t, f in enumerate(projected, start=1)]
    tv = projected[-1] * (1 + terminal_growth) / (discount - terminal_growth)
    pv_tv = tv / (1 + discount) ** years
    ev = sum(pv) + pv_tv
    equity = ev - (net_debt or 0)
    return DCFResult(per_share=equity / shares, enterprise_value=ev, equity_value=equity, pv_fcf=pv,
                     pv_terminal=pv_tv, projected_fcf=projected)


def dcf_default_growth(analyst_growth: Optional[float], fcf_cagr_3y: Optional[float]) -> tuple[float, str]:
    """growth = min(analyst growth estimate or 3-year FCF CAGR, 20%), floored at -10%."""
    if analyst_growth is not None:
        g, src = analyst_growth, "analysts' expected EPS growth"
    elif fcf_cagr_3y is not None:
        g, src = fcf_cagr_3y, "3-year free cash flow growth (CAGR)"
    else:
        g, src = 0.05, "default 5% (no growth data available)"
    return max(min(g, 0.20), -0.10), src


def dcf_scenarios(fcf0, growth, discount, terminal, net_debt, shares) -> dict[str, DCFResult]:
    """Bear / base / bull = growth -5 percentage points, base, +5 points."""
    return {name: dcf(fcf0, growth + delta, discount, terminal, net_debt, shares)
            for name, delta in (("Bear", -0.05), ("Base", 0.0), ("Bull", 0.05))}


# =========================================================================== peers
PEER_FIELDS = {  # our name -> yfinance info key
    "market_cap": "marketCap",
    "pe": "trailingPE",
    "ps": "priceToSalesTrailing12Months",
    "ev_ebitda": "enterpriseToEbitda",
    "revenue_growth": "revenueGrowth",
    "net_margin": "profitMargins",
    "roe": "returnOnEquity",
}


def peer_row(symbol: str, info: Optional[dict]) -> dict:
    row = {"ticker": symbol, "name": None}
    if not info:
        return row
    row["name"] = info.get("shortName") or info.get("longName")
    for ours, key in PEER_FIELDS.items():
        v = info.get(key)
        try:
            v = float(v) if v is not None else None
        except (TypeError, ValueError):
            v = None
        if ours in ("pe", "ev_ebitda") and v is not None and v <= 0:
            v = None  # negative multiples are not meaningful
        row[ours] = v
    if row.get("pe") is None and (info.get("trailingEps") or 0) < 0:
        row["pe_note"] = "negative earnings"
    return row


def peer_medians(peers: pd.DataFrame) -> dict[str, Optional[float]]:
    out = {}
    for f in PEER_FIELDS:
        if f in peers:
            s = pd.to_numeric(peers[f], errors="coerce").dropna()
            out[f] = float(s.median()) if len(s) else None
    return out
