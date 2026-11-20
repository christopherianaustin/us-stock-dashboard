"""Builds the Earnings tab data. Source priority for estimates: yfinance, then Finnhub."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional

import pandas as pd

from core.earnings import (beat_rate, classify, match_quarter, price_reaction, revisions_table, surprise_pct,
                           typical_move, unrounded_estimate)
from core.financials import Financials, period_label
from core.logging_setup import get_logger
from core.models import Source
from core.providers import registry
from core.providers.sec_edgar import SecEdgarClient
from core.price_service import _earnings_table

log = get_logger("earnings_service")

PERIOD_LABELS = {"0q": "Current quarter", "+1q": "Next quarter", "0y": "Current fiscal year", "+1y": "Next fiscal year"}


@dataclass
class EarningsData:
    symbol: str
    history: pd.DataFrame                 # one row per past quarter (newest last)
    beat_rate_8: tuple
    beat_rate_12: tuple
    typical_move: Optional[float]
    upcoming: dict[str, Any]
    revisions: pd.DataFrame               # EPS estimate trend
    revision_counts: pd.DataFrame         # up / down revisions in the last 7 / 30 days
    revenue_estimates: pd.DataFrame
    finnhub_check: pd.DataFrame
    estimates_source: str
    warnings: list[str] = field(default_factory=list)


def _quarters(fin: Optional[Financials]) -> pd.DataFrame:
    if fin is None or not fin.available:
        return pd.DataFrame(columns=["period_end", "fiscal_year", "fiscal_quarter"])
    return fin.periods("Q", 80)


def _filing_links(subs: dict, history: pd.DataFrame) -> tuple[list, list]:
    """10-Q/10-K whose report date = the quarter end; 8-K with item 2.02 filed within 3 days of the call."""
    if not subs:
        return [None] * len(history), [None] * len(history)
    periodic = SecEdgarClient.recent_filings(subs, forms={"10-Q", "10-K", "20-F", "40-F"}, limit=None)
    eightk = [f for f in SecEdgarClient.recent_filings(subs, forms={"8-K"}, limit=None) if f.items and "2.02" in f.items]
    q_links, k_links = [], []
    for _, r in history.iterrows():
        pe = r["period_end"].date() if pd.notna(r["period_end"]) else None
        q = next((f for f in periodic if f.report_date and pe and abs((f.report_date - pe).days) <= 3), None)
        q_links.append((q.url or q.index_url, q.form) if q else None)
        d = r["date"].date()
        k = next((f for f in eightk if f.filing_date and 0 <= (f.filing_date - d).days <= 3), None)
        k_links.append(k.index_url if k else None)
    return q_links, k_links


def load_earnings(symbol: str, cik: Optional[str], fin: Optional[Financials]) -> Optional[EarningsData]:
    yf, fh, sec = registry.yfinance(), registry.finnhub(), registry.sec()
    warnings: list[str] = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        futs = {
            "dates": pool.submit(yf.get_earnings_dates, symbol, 60),
            "trend": pool.submit(yf.get_eps_trend, symbol),
            "revs": pool.submit(yf.get_eps_revisions, symbol),
            "eps_est": pool.submit(yf.get_earnings_estimate, symbol),
            "rev_est": pool.submit(yf.get_revenue_estimate, symbol),
            "hist": pool.submit(registry.get_history, symbol, "5y"),
            "fh": pool.submit(fh.get_earnings_surprises, symbol) if fh.enabled else None,
            "fh_cal": pool.submit(fh.get_earnings_calendar, symbol) if fh.enabled else None,
            "subs": pool.submit(sec.get_submissions, cik) if cik else None,
        }
        res = {}
        for k, f in futs.items():
            try:
                res[k] = f.result() if f is not None else None
            except Exception as exc:  # noqa: BLE001 - one source failing must not break the tab
                log.warning("earnings source %s failed for %s: %s", k, symbol, exc)
                res[k] = None

    table = _earnings_table(res["dates"])
    today = pd.Timestamp(date.today())
    past = table[(table["date"] <= today) & table["eps_reported"].notna()].copy()
    source = Source.YFINANCE.value

    # Fallback: Finnhub surprises if yfinance has none
    if past.empty and res["fh"]:
        rows = [{"date": pd.Timestamp(r["period"]) + pd.Timedelta(days=30), "datetime": None,
                 "eps_estimate": r.get("estimate"), "eps_reported": r.get("actual"),
                 "surprise_pct": r.get("surprisePercent"), "timing": "unknown"} for r in res["fh"]]
        past = pd.DataFrame(rows).sort_values("date")
        source = Source.FINNHUB.value
        warnings.append("Earnings history comes from Finnhub (yfinance had none); dates are approximate.")
    if past.empty:
        warnings.append("No earnings history available for this company.")

    past = past.tail(12).reset_index(drop=True)
    past["surprise_pct"] = [s if pd.notna(s) else surprise_pct(a, e)
                            for s, a, e in zip(past["surprise_pct"], past["eps_reported"], past["eps_estimate"])]
    past["result"] = past["surprise_pct"].map(classify)
    past["eps_estimate"] = [unrounded_estimate(a, e, s) for a, e, s in
                            zip(past["eps_reported"], past["eps_estimate"], past["surprise_pct"])]

    # Fiscal quarter, GAAP EPS and actual revenue from SEC
    quarters = _quarters(fin)
    matched = [match_quarter(d, quarters) for d in past["date"]]
    past["period_end"] = [m["period_end"] if m else pd.NaT for m in matched]
    past["quarter"] = [(period_label(m["fiscal_year"], m["fiscal_quarter"], "Q") + (" (est.)" if m["estimated"] else ""))
                       if m else f"{d:%b %Y}" for m, d in zip(matched, past["date"])]
    gaap = fin.series("eps_diluted", "Q") if fin is not None else pd.Series(dtype=float)
    rev = fin.series("revenue", "Q") if fin is not None else pd.Series(dtype=float)
    past["eps_gaap"] = [gaap.get(pe) if pd.notna(pe) else None for pe in past["period_end"]]
    past["revenue"] = [rev.get(pe) if pd.notna(pe) else None for pe in past["period_end"]]

    # Revenue estimates (only where Finnhub's calendar has them, usually the latest quarter)
    cal = pd.DataFrame(res["fh_cal"] or [])
    past["revenue_estimate"] = None
    if not cal.empty and "revenueEstimate" in cal:
        cal["d"] = pd.to_datetime(cal["date"])
        for i, d in enumerate(past["date"]):
            m = cal[(cal["d"] - d).abs() <= pd.Timedelta(days=3)]
            if not m.empty and pd.notna(m["revenueEstimate"].iloc[0]):
                past.at[i, "revenue_estimate"] = float(m["revenueEstimate"].iloc[0])

    # Post-earnings price reaction
    hist_df, _prov = res["hist"] or (None, None)
    m1, m5 = [None] * len(past), [None] * len(past)
    if hist_df is not None and not hist_df.empty:
        close = hist_df["Close"].copy()
        close.index = pd.DatetimeIndex(close.index).tz_localize(None).normalize()
        for i, r in past.iterrows():
            rx = price_reaction(close, r["date"], r["timing"])
            m1[i], m5[i] = rx.move_1d, rx.move_5d
    else:
        warnings.append("Price history unavailable, so post-earnings moves can't be calculated.")
    past["move_1d"], past["move_5d"] = m1, m5

    q_links, k_links = _filing_links(res["subs"] or {}, past)
    # Companies with very many filings (e.g. banks) only have the last few months in the SEC "recent" list;
    # fall back to the company's 10-Q / 10-K / 8-K list on EDGAR.
    browse = (f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type={{t}}&dateb=&owner=include&count=40"
              if cik else None)
    past["filing_url"] = [q[0] if q else (browse.format(t="10-") if browse else None) for q in q_links]
    past["filing_form"] = [q[1] if q else ("EDGAR list" if browse else None) for q in q_links]
    past["press_release_url"] = [k if k else (browse.format(t="8-K") if browse else None) for k in k_links]
    past["press_release_exact"] = [k is not None for k in k_links]

    # Upcoming earnings
    upcoming: dict[str, Any] = {}
    fut = table[table["date"] > today - pd.Timedelta(days=0)]
    fut = fut[fut["eps_reported"].isna()].sort_values("date")
    if not fut.empty:
        r = fut.iloc[0]
        upcoming.update({"date": r["date"], "timing": r["timing"], "days": (r["date"] - today).days})
    eps_est, rev_est = res["eps_est"], res["rev_est"]
    if eps_est is not None and "0q" in eps_est.index:
        upcoming.update({"eps_estimate": eps_est.loc["0q", "avg"], "eps_low": eps_est.loc["0q", "low"],
                         "eps_high": eps_est.loc["0q", "high"], "analysts": eps_est.loc["0q", "numberOfAnalysts"],
                         "year_ago_eps": eps_est.loc["0q"].get("yearAgoEps")})
    if rev_est is not None and "0q" in rev_est.index:
        upcoming.update({"revenue_estimate": rev_est.loc["0q", "avg"], "revenue_analysts": rev_est.loc["0q", "numberOfAnalysts"]})

    # Revisions
    rev_tbl = revisions_table(res["trend"])
    if not rev_tbl.empty:
        rev_tbl.index = [PERIOD_LABELS.get(i, i) for i in rev_tbl.index]
    counts = pd.DataFrame()
    if res["revs"] is not None:
        counts = res["revs"].drop(columns=[c for c in ("currency", "methodology") if c in res["revs"]], errors="ignore")
        counts.index = [PERIOD_LABELS.get(i, i) for i in counts.index]
        counts = counts.rename(columns={"upLast7days": "Up (7 days)", "upLast30days": "Up (30 days)",
                                        "downLast30days": "Down (30 days)", "downLast7Days": "Down (7 days)"})
    rev_estimates = pd.DataFrame()
    if rev_est is not None:
        rev_estimates = rev_est.drop(columns=[c for c in ("currency",) if c in rev_est], errors="ignore")
        rev_estimates.index = [PERIOD_LABELS.get(i, i) for i in rev_estimates.index]

    # Cross-check with Finnhub (last ~4 quarters)
    check = pd.DataFrame()
    if res["fh"]:
        rows = []
        for r in res["fh"]:
            # Finnhub labels quarters by calendar dates, which don't match non-calendar fiscal years.
            # Match on the reported EPS within ~4 months, else on the nearest quarter end.
            per = pd.Timestamp(r["period"])
            near = past[(past["period_end"] - per).abs() <= pd.Timedelta(days=120)] if not past.empty else past
            m = near[(near["eps_reported"] - (r.get("actual") or 0)).abs() <= 0.011] if r.get("actual") is not None else near.iloc[0:0]
            if m.empty and not near.empty:
                m = near.loc[[(near["period_end"] - per).abs().idxmin()]]
            rows.append({"period": r["period"], "Finnhub estimate": r.get("estimate"), "Finnhub actual": r.get("actual"),
                         "yfinance estimate": m["eps_estimate"].iloc[0] if len(m) else None,
                         "yfinance actual": m["eps_reported"].iloc[0] if len(m) else None})
        check = pd.DataFrame(rows)

    return EarningsData(
        symbol=symbol, history=past, beat_rate_8=beat_rate(past["result"], 8), beat_rate_12=beat_rate(past["result"], 12),
        typical_move=typical_move(past["move_1d"]), upcoming=upcoming, revisions=rev_tbl, revision_counts=counts,
        revenue_estimates=rev_estimates, finnhub_check=check, estimates_source=source, warnings=warnings)
