"""Loads data for the Dividends, Ownership & Sentiment and News & Filings tabs.
Source priority: analyst ratings Finnhub -> yfinance; news Finnhub -> yfinance (SPEC 4.5)."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional

import pandas as pd

from core.dividends import DividendSummary, annual_dps, summarize, yield_history
from core.financials import Financials
from core.logging_setup import get_logger
from core.models import Filing, Source
from core.providers import registry
from core.providers.sec_edgar import SecEdgarClient
from core.sentiment import (clean_news, consensus_summary, holder_breakdown, insider_monthly_net, insider_table,
                            news_from_finnhub, news_from_yfinance, recommendations_from_finnhub,
                            recommendations_from_yfinance, upgrades_table)

log = get_logger("extras")


def _safe(fn, *args):
    try:
        return fn(*args)
    except Exception as exc:  # noqa: BLE001 - one source failing must not break the tab
        log.warning("%s failed: %s", getattr(fn, "__name__", fn), exc)
        return None


# =========================================================================== dividends
@dataclass
class DividendData:
    symbol: str
    summary: DividendSummary
    dividends: pd.Series
    annual: pd.Series
    yield_hist: pd.Series
    payout_ratio: Optional[float]
    fcf_payout: Optional[float]
    payout_hist: pd.Series
    next_ex_date: Optional[date]
    sec_dps: pd.Series           # dividends declared per share, by fiscal year (SEC cross-check)


def load_dividends(symbol: str, price: Optional[float], fin: Optional[Financials],
                   quarterly: Optional[pd.DataFrame]) -> Optional[DividendData]:
    yf = registry.yfinance()
    with ThreadPoolExecutor(max_workers=3) as pool:
        f_div = pool.submit(_safe, yf.get_dividends, symbol)
        f_hist = pool.submit(_safe, registry.get_history, symbol, "5y")
        f_cal = pool.submit(_safe, yf.get_calendar, symbol)
        divs, hist, cal = f_div.result(), f_hist.result(), f_cal.result()
    if divs is None:
        return None
    close = None
    if hist and hist[0] is not None:
        c = hist[0]["Close"].copy()
        c.index = pd.DatetimeIndex(c.index).tz_localize(None).normalize()
        close = c
    summ = summarize(divs, close, price)

    payout = fcf_payout = None
    payout_hist = pd.Series(dtype=float)
    if quarterly is not None and not quarterly.empty and "dividends_paid_ttm" in quarterly:
        q = quarterly
        ni, dp, fcf = q["net_income_ttm"], q["dividends_paid_ttm"], q["fcf_ttm"]
        payout_hist = (dp / ni.where(ni > 0)).dropna().tail(20)
        last = q.dropna(subset=["dividends_paid_ttm"]).tail(1)
        if not last.empty:
            r = last.iloc[0]
            payout = r["dividends_paid_ttm"] / r["net_income_ttm"] if r["net_income_ttm"] > 0 else None
            fcf_payout = r["dividends_paid_ttm"] / r["fcf_ttm"] if pd.notna(r["fcf_ttm"]) and r["fcf_ttm"] > 0 else None

    nxt = (cal or {}).get("Ex-Dividend Date")
    next_ex = nxt if isinstance(nxt, date) and nxt >= date.today() else None
    sec_dps = pd.Series(dtype=float)
    if fin is not None:
        r = fin.rows("dividends_per_share", "FY")
        if not r.empty:
            sec_dps = pd.Series(r["value"].values, index=r["fiscal_year"].astype(int).values).groupby(level=0).last()
    return DividendData(
        symbol=symbol, summary=summ, dividends=divs, annual=annual_dps(divs) if len(divs) else pd.Series(dtype=float),
        yield_hist=yield_history(divs, close) if (close is not None and summ.pays) else pd.Series(dtype=float),
        payout_ratio=payout, fcf_payout=fcf_payout, payout_hist=payout_hist, next_ex_date=next_ex, sec_dps=sec_dps)


# =========================================================================== ownership & sentiment
@dataclass
class OwnershipData:
    symbol: str
    breakdown: Optional[dict[str, float]]
    institutions_count: Optional[int]
    top_institutions: pd.DataFrame
    insiders: pd.DataFrame
    insider_monthly: pd.DataFrame
    recommendations: pd.DataFrame
    rec_source: Optional[str]
    consensus: Optional[dict]
    upgrades: pd.DataFrame
    short: dict[str, Any]
    target: dict[str, Any]


def load_ownership(symbol: str) -> OwnershipData:
    yf, fh = registry.yfinance(), registry.finnhub()
    with ThreadPoolExecutor(max_workers=7) as pool:
        f = {k: pool.submit(_safe, fn, symbol) for k, fn in {
            "major": yf.get_major_holders, "inst": yf.get_institutional_holders,
            "insider": yf.get_insider_transactions, "yf_rec": yf.get_recommendations,
            "updown": yf.get_upgrades_downgrades, "info": yf.get_profile, "targets": yf.get_price_targets}.items()}
        if fh.enabled:
            f["fh_rec"] = pool.submit(_safe, fh.get_recommendation_trends, symbol)
        r = {k: v.result() for k, v in f.items()}

    major = r.get("major")
    count = None
    if major is not None and not major.empty and "institutionsCount" in major.index:
        count = int(major.iloc[:, 0]["institutionsCount"])
    inst = r.get("inst")
    top = pd.DataFrame()
    if inst is not None and not inst.empty:
        top = inst.head(10).rename(columns={"Date Reported": "date reported", "Holder": "holder", "pctHeld": "% of shares",
                                            "Shares": "shares", "Value": "value", "pctChange": "change in shares"})
    ins = insider_table(r.get("insider"))
    rec = recommendations_from_finnhub(r.get("fh_rec"))
    src = Source.FINNHUB.value if not rec.empty else None
    if rec.empty:
        rec = recommendations_from_yfinance(r.get("yf_rec"))
        src = Source.YFINANCE.value if not rec.empty else None
    info = r.get("info") or {}
    sdate = info.get("dateShortInterest")
    return OwnershipData(
        symbol=symbol, breakdown=holder_breakdown(major), institutions_count=count, top_institutions=top,
        insiders=ins, insider_monthly=insider_monthly_net(ins), recommendations=rec.tail(12), rec_source=src,
        consensus=consensus_summary(rec), upgrades=upgrades_table(r.get("updown")),
        short={"pct_float": info.get("shortPercentOfFloat"), "days_to_cover": info.get("shortRatio"),
               "shares_short": info.get("sharesShort"),
               "as_of": pd.Timestamp(sdate, unit="s").date() if sdate else None},
        target=r.get("targets") or {})


# =========================================================================== news & filings
@dataclass
class NewsData:
    symbol: str
    items: list[dict]
    source: Optional[str]
    filings: list[Filing] = field(default_factory=list)
    filings_note: Optional[str] = None


FILING_FORMS = {"8-K", "8-K/A", "10-Q", "10-Q/A", "10-K", "10-K/A", "4", "20-F", "6-K", "DEF 14A", "S-1", "SC 13G",
                "SC 13D", "SC 13G/A", "SC 13D/A"}


def load_news(symbol: str, cik: Optional[str]) -> NewsData:
    yf, fh, sec = registry.yfinance(), registry.finnhub(), registry.sec()
    with ThreadPoolExecutor(max_workers=3) as pool:
        f_fh = pool.submit(_safe, fh.get_company_news, symbol, 30) if fh.enabled else None
        f_yf = pool.submit(_safe, yf.get_news, symbol)
        f_sub = pool.submit(_safe, sec.get_submissions, cik) if cik else None
        fh_rows = f_fh.result() if f_fh else None
        yf_rows = f_yf.result()
        subs = f_sub.result() if f_sub else None
    items, src = news_from_finnhub(fh_rows), Source.FINNHUB.value
    if not items:
        items, src = news_from_yfinance(yf_rows), Source.YFINANCE.value
    items = clean_news(items, days=30, limit=60)
    filings, note = [], None
    if subs:
        filings = SecEdgarClient.recent_filings(subs, forms=FILING_FORMS, limit=200)
    elif cik is None:
        note = "This company is not in the SEC company list, so no SEC filings are shown."
    else:
        note = "SEC filings could not be loaded right now."
    return NewsData(symbol=symbol, items=items, source=src if items else None, filings=filings, filings_note=note)
