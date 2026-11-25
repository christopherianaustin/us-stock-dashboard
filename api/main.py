"""FastAPI: the same data as the dashboard, as JSON, so the mobile team can see the contract (SPEC Section 11).

Run:   uvicorn api.main:app --reload
Docs:  http://localhost:8000/docs

Every value carries `source`, `license_tag` and `as_of`. When production-safe mode is on (PRODUCTION_SAFE_MODE=true
in .env, or ?safe_mode=true on any request), every DEMO_ONLY value is replaced by
{"value": null, "na_reason": "Requires a licensed data provider"}.
"""
from __future__ import annotations

import dataclasses
import math
import threading
import time
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Literal, Optional

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Path, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from config.settings import settings
from core.bundle import Bundle, load_bundle
from core.company import TickerNotFound, resolve_ticker
from core.coverage import coverage_rows, coverage_summary
from core.financials import field_label, field_specs, DERIVED_FIELDS
from core.models import DataPoint, LicenseTag, Source
from core.providers import registry
from core.ratios import METRICS
from core.scorecard import PILLARS, insight_texts
from core.valuation import dcf_scenarios

SAFE_TEXT = "Requires a licensed data provider"
DEMO = LicenseTag.DEMO_ONLY.value

app = FastAPI(
    title="US Stock Dashboard API (Nanovest demo)",
    version="0.8.0",
    description=(
        "Per-symbol US stock analysis as JSON. **Demo only**: some sources (yfinance, Finnhub free) are not licensed "
        "for commercial use; every value says where it came from (`source`) and whether it is commercially usable "
        "(`license_tag`: COMMERCIAL_OK, CALCULATED_SAFE, DEMO_ONLY).\n\n"
        "This information is for educational purposes only and is not investment advice."
    ),
)


# The Phase 9 mobile prototype (Vite dev server / preview) runs on your own computer and calls this API from the browser.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://(127\.0\.0\.1|localhost|192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+):(5173|4173)",
    allow_methods=["GET"],
    allow_headers=["*"],
)


# =========================================================================== response models (for /docs)
class Value(BaseModel):
    """One value with its origin. `value` is null when not available; `na_reason` explains why."""
    value: Any = None
    source: Optional[str] = None
    license_tag: Optional[str] = None
    as_of: Optional[str] = None
    derived: bool = False
    na_reason: Optional[str] = None
    note: Optional[str] = None


class Envelope(BaseModel):
    ticker: str
    generated_at: str
    production_safe_mode: bool
    disclaimer: str = ("This information is for educational purposes only and is not investment advice. Past "
                       "performance does not guarantee future results. Data may be delayed or inaccurate.")
    warnings: list[str] = Field(default_factory=list)
    data: dict[str, Any]


# =========================================================================== helpers
_cache: dict[str, tuple[float, Bundle]] = {}
_lock = threading.Lock()
_sym_locks: dict[str, threading.Lock] = {}
BUNDLE_TTL = 120  # seconds; underlying sources have their own disk cache (Section 10 TTLs)


def get_bundle(ticker: str) -> Bundle:
    try:
        resolved = resolve_ticker(ticker)
    except TickerNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    with _lock:
        sym_lock = _sym_locks.setdefault(resolved.symbol, threading.Lock())
    # One load per symbol: when the mobile prototype asks for several sections at once, they wait for one load.
    with sym_lock:
        with _lock:
            hit = _cache.get(resolved.symbol)
            if hit and time.time() - hit[0] < BUNDLE_TTL:
                return hit[1]
        b = load_bundle(resolved)
        with _lock:
            _cache[resolved.symbol] = (time.time(), b)
        return b


def is_safe(param: Optional[bool]) -> bool:
    return settings.production_safe_mode if param is None else param


def clean(x: Any) -> Any:
    """Make anything JSON-safe: numpy -> python, NaN -> None, timestamps -> ISO strings, enums -> values."""
    if x is None:
        return None
    if isinstance(x, Enum):
        return x.value
    if x is pd.NaT:
        return None
    if isinstance(x, (pd.Timestamp, datetime)):
        ts = pd.Timestamp(x)
        # plain dates (midnight, no timezone) are shown as YYYY-MM-DD
        return ts.date().isoformat() if ts.tzinfo is None and ts == ts.normalize() else ts.isoformat()
    if isinstance(x, date):
        return x.isoformat()
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (float, np.floating)):
        f = float(x)
        return None if math.isnan(f) or math.isinf(f) else f
    if isinstance(x, (np.bool_,)):
        return bool(x)
    if isinstance(x, dict):
        return {str(k): clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple, set)):
        return [clean(v) for v in x]
    if isinstance(x, pd.DataFrame):
        return [clean(r) for r in x.reset_index().to_dict("records")] if not isinstance(x.index, pd.RangeIndex) \
            else [clean(r) for r in x.to_dict("records")]
    if isinstance(x, pd.Series):
        return {clean(k) if not isinstance(k, str) else k: clean(v) for k, v in x.items()}
    if dataclasses.is_dataclass(x):
        return clean(dataclasses.asdict(x))
    if isinstance(x, BaseModel):
        return clean(x.model_dump())
    return x


def val(dp: Optional[DataPoint], safe: bool) -> dict:
    if dp is None:
        return Value(na_reason="Not available").model_dump()
    if safe and dp.license_tag == LicenseTag.DEMO_ONLY:
        return Value(source=clean(dp.source), license_tag=DEMO, na_reason=SAFE_TEXT).model_dump()
    return Value(value=clean(dp.value), source=clean(dp.source), license_tag=clean(dp.license_tag),
                 as_of=clean(dp.as_of), derived=dp.derived, na_reason=dp.na_reason, note=dp.note).model_dump()


def raw(value: Any, source: str, license_tag: str, safe: bool, as_of: Any = None, note: Optional[str] = None) -> dict:
    """Wrap a plain value with its origin (redacted in safe mode if demo-only)."""
    if safe and license_tag == DEMO:
        return Value(source=source, license_tag=license_tag, na_reason=SAFE_TEXT).model_dump()
    v = clean(value)
    return Value(value=v, source=source, license_tag=license_tag, as_of=clean(as_of), note=note,
                 na_reason=None if v not in (None, [], {}) else "Not available").model_dump()


def block(data: Any, source: str, license_tag: str, safe: bool, as_of: Any = None) -> dict:
    """A list / table with one origin for the whole block."""
    if safe and license_tag == DEMO:
        return {"available": False, "source": source, "license_tag": license_tag, "na_reason": SAFE_TEXT, "items": []}
    return {"available": data is not None and len(data) > 0, "source": source, "license_tag": license_tag,
            "as_of": clean(as_of) or date.today().isoformat(), "items": clean(data) if data is not None else []}


def envelope(b: Bundle, safe: bool, data: dict, extra_warnings: Optional[list[str]] = None) -> Envelope:
    warnings = [f"{k} could not be loaded" for k in b.errors] + list(b.header.warnings) + (extra_warnings or [])
    return Envelope(ticker=b.resolved.symbol, generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    production_safe_mode=safe, warnings=warnings, data=clean(data))


TickerPath = Path(..., description="US ticker, e.g. AAPL, JPM, BRK.B (BRK-B also works)", examples=["AAPL"])
SafeQuery = Query(None, description="Override PRODUCTION_SAFE_MODE for this request (true = hide DEMO_ONLY values)")


# =========================================================================== endpoints
@app.get("/", include_in_schema=False)
def root():
    return {"message": "US Stock Dashboard API. Open /docs for the interactive documentation."}


@app.get("/stocks/{ticker}/summary", response_model=Envelope, tags=["stocks"],
         summary="Header, scorecard, key stats, strengths and risks")
def summary(ticker: str = TickerPath, safe_mode: Optional[bool] = SafeQuery,
            lang: Literal["en", "id"] = Query("en", description="Language of labels and insights")):
    b, safe = get_bundle(ticker), is_safe(safe_mode)
    h, p = b.header, b.header.profile
    sc = b.scorecard(lang=lang, safe_mode=safe)
    txt = insight_texts(lang)
    header = {k: val(getattr(h, k), safe) for k in ("price", "change", "change_pct", "market_cap", "week52_high",
                                                     "week52_low", "next_earnings_date", "data_freshness")}
    header.update({k: val(getattr(p, k), safe) for k in ("name", "exchange", "sector", "industry", "logo_url")})
    scorecard = []
    if sc:
        for k in PILLARS:
            ps = sc.pillars[k]
            scorecard.append({"pillar": k, "label": txt["pillars"][k], "score": ps.score,
                              "level": ps.level, "level_label": txt["levels"].get(ps.level or "na"),
                              "metrics_used": ps.used, "metrics_total": ps.total,
                              "explanation": txt["pillar_help"][k],
                              "license_tag": LicenseTag.CALCULATED_SAFE.value if safe else "MIXED"})
    snap = b.analysis.snapshot if b.analysis else {}
    key_stats = {k: {**val(snap.get(k), safe), "label": METRICS[k][0], "unit": METRICS[k][1]}
                 for k in ("pe", "ps", "ev_ebitda", "revenue_yoy", "net_margin", "roe", "debt_to_equity")}
    if b.dividends is not None and b.dividends.summary.pays:
        key_stats["dividend_yield"] = {**raw(b.dividends.summary.yield_ttm, "yfinance", DEMO, safe), "unit": "ratio"}
    if b.price is not None:
        key_stats["beta"] = {**raw(b.price.risk.beta, "Calculated", DEMO, safe), "unit": "x"}
    return envelope(b, safe, {
        "header": header, "scorecard": scorecard,
        "scorecard_note": "Our description of the data per category (Strong / Neutral / Weak). Not a recommendation.",
        "strengths": [i.text for i in sc.strengths] if sc else [],
        "risks": [i.text for i in sc.risks] if sc else [],
        "key_stats": key_stats,
        "peer_medians": raw(b.analysis.peer_medians if b.analysis else None, "yfinance", DEMO, safe),
    })


STATEMENT_FIELDS = {
    "income": [f for f, s in field_specs().items() if s.statement == "income"] +
              [f for f, d in DERIVED_FIELDS.items() if d[1] == "income"],
    "balance": [f for f, s in field_specs().items() if s.statement == "balance"] +
               [f for f, d in DERIVED_FIELDS.items() if d[1] == "balance"],
    "cashflow": [f for f, s in field_specs().items() if s.statement == "cashflow"] +
                [f for f, d in DERIVED_FIELDS.items() if d[1] == "cashflow"],
}


@app.get("/stocks/{ticker}/financials", response_model=Envelope, tags=["stocks"],
         summary="Income statement, balance sheet or cash flow (quarterly or annual)")
def financials(ticker: str = TickerPath, safe_mode: Optional[bool] = SafeQuery,
               period: Literal["quarterly", "annual"] = "quarterly",
               statement: Literal["income", "balance", "cashflow"] = "income",
               periods: int = Query(12, ge=1, le=40, description="Number of most recent periods")):
    b, safe = get_bundle(ticker), is_safe(safe_mode)
    fin = b.fin
    if fin is None or not fin.available:
        raise HTTPException(404, "No financial statements available for this company.")
    ptype = "Q" if period == "quarterly" else "FY"
    per = fin.periods(ptype, periods)
    t = fin.tidy[(fin.tidy["period_type"] == ptype) & fin.tidy["field"].isin(STATEMENT_FIELDS[statement])
                 & fin.tidy["period_end"].isin(per["period_end"])].copy()
    hidden = safe and fin.source != Source.SEC.value
    rows = [] if hidden else [{
        "field": r.field, "label": field_label(r.field), "period_end": r.period_end, "fiscal_year": r.fiscal_year,
        "fiscal_quarter": r.fiscal_quarter, "period_type": r.period_type, "value": r.value, "unit": r.unit,
        "source": r.source, "license_tag": r.license_tag, "derived": r.derived, "method": r.method,
        "as_of": r.first_filed} for r in t.sort_values(["field", "period_end"]).itertuples()]
    missing = {f: fin.na_reason(f) for f in STATEMENT_FIELDS[statement] if fin.na_reason(f)}
    return envelope(b, safe, {
        "statement": statement, "period": period, "source": fin.source,
        "periods": [{"period_end": r.period_end, "label": r.label} for r in per.itertuples()],
        "rows": rows, "not_available": missing,
        "note": "as_of = date the value was first filed with the SEC. derived = calculated by us (e.g. Q4 = FY - Q1-Q3).",
    }, [SAFE_TEXT] if hidden else None)


@app.get("/stocks/{ticker}/ratios", response_model=Envelope, tags=["stocks"], summary="All ratios (current values)")
def ratios(ticker: str = TickerPath, safe_mode: Optional[bool] = SafeQuery):
    b, safe = get_bundle(ticker), is_safe(safe_mode)
    if b.analysis is None:
        raise HTTPException(404, "Ratios need financial statements, which are not available.")
    out = {k: {**val(dp, safe), "label": METRICS.get(k, (k,))[0], "unit": METRICS.get(k, ("", ""))[1],
               "group": METRICS.get(k, ("", "", ""))[2]} for k, dp in b.analysis.snapshot.items()}
    a = b.analysis
    out["piotroski"] = {**raw(a.piotroski.score if a.piotroski.tested else None, "Calculated", LicenseTag.CALCULATED_SAFE.value, safe),
                        "tests_run": a.piotroski.tested, "fiscal_year": a.piotroski.fiscal_year,
                        "checks": clean([dataclasses.asdict(c) for c in a.piotroski.checks])}
    out["altman_z"] = {**raw(a.altman.z, "Calculated", DEMO, safe), "zone": None if safe else a.altman.zone,
                       "na_reason": a.altman.reason}
    return envelope(b, safe, out)


@app.get("/stocks/{ticker}/valuation", response_model=Envelope, tags=["stocks"],
         summary="Valuation history, peers, Graham number, DCF, analyst targets")
def valuation(ticker: str = TickerPath, safe_mode: Optional[bool] = SafeQuery,
              growth: Optional[float] = Query(None, description="DCF yearly FCF growth, e.g. 0.08 (default: model default)"),
              discount: float = Query(0.10, gt=0, lt=0.5), terminal: float = Query(0.025, ge=0, lt=0.1)):
    b, safe = get_bundle(ticker), is_safe(safe_mode)
    a = b.analysis
    if a is None:
        raise HTTPException(404, "Valuation needs financial statements, which are not available.")
    hist = a.history.resample("W-FRI").last().dropna(how="all") if not a.history.empty else pd.DataFrame()
    d = a.dcf_inputs
    g = growth if growth is not None else d["growth"]
    dcf_out: dict[str, Any] = {"na_reason": d.get("not_meaningful")}
    if not d.get("not_meaningful"):
        sc = dcf_scenarios(d["fcf0"], g, discount, terminal, d["net_debt"], d["shares"])
        dcf_lic = DEMO if (growth is None and not d["growth_source"].startswith("3-year")) else LicenseTag.CALCULATED_SAFE.value
        dcf_out = {"label": "Estimate based on assumptions. Not a prediction.",
                   "assumptions": {"fcf_ttm": d["fcf0"], "growth": g,
                                   "growth_source": d["growth_source"] if growth is None else "user input",
                                   "discount_rate": discount, "terminal_growth": terminal, "net_debt": d["net_debt"],
                                   "shares": d["shares"]},
                   "scenarios": {k: raw(v.per_share, "Calculated", dcf_lic, safe, note=v.reason) for k, v in sc.items()}}
    return envelope(b, safe, {
        "history_weekly": block(hist.reset_index(names="date") if not hist.empty else None, "Calculated (SEC + daily prices)",
                                a.history_license.value, safe),
        "history_stats": {k: raw(dataclasses.asdict(s), "Calculated", a.history_license.value, safe) for k, s in a.stats.items()},
        "peers": block(a.peers, "yfinance", DEMO, safe),
        "peer_medians": raw(a.peer_medians, "yfinance", DEMO, safe),
        "graham_number": val(a.graham, safe),
        "dcf": dcf_out,
        "analyst_targets": raw({"low": a.estimates.target_low, "mean": a.estimates.target_mean,
                                "high": a.estimates.target_high} if a.estimates.target_mean else None,
                               "yfinance", DEMO, safe, note="Wall Street analysts' price targets (third-party opinion)"),
    })


RANGE_DAYS = {"1m": 1, "3m": 3, "6m": 6, "1y": 12, "3y": 36, "5y": 60}


@app.get("/stocks/{ticker}/technicals", response_model=Envelope, tags=["stocks"],
         summary="Price history with indicators, signals, support/resistance, pivots, risk, returns")
def technicals(ticker: str = TickerPath, safe_mode: Optional[bool] = SafeQuery,
               range: Literal["1m", "3m", "6m", "1y", "3y", "5y"] = "1y",  # noqa: A002 - name from the spec
               sr_window: Literal["6m", "1y", "2y"] = "1y"):
    b, safe = get_bundle(ticker), is_safe(safe_mode)
    p = b.price
    if p is None:
        raise HTTPException(404, "Price history is not available.")
    lic = p.license_tag.value
    start = p.df.index[-1] - pd.DateOffset(months=RANGE_DAYS[range])
    bars = p.df[p.df.index >= start].round(4).reset_index(names="date")
    sr = p.sr[sr_window]
    return envelope(b, safe, {
        "range": range, "source": p.source.value,
        "bars": block(bars, f"{p.source.value} + calculated indicators", lic, safe),
        "snapshot": raw(dataclasses.asdict(p.snap), "Calculated", lic, safe),
        "signals": block([dataclasses.asdict(s) for s in p.signals], "Calculated", lic, safe),
        "support_resistance": raw({"supports": [dataclasses.asdict(l) for l in sr.supports],
                                   "resistances": [dataclasses.asdict(l) for l in sr.resistances],
                                   "tolerance": sr.tolerance, "window": sr.window}, "Calculated", lic, safe,
                                  note="Support and resistance are areas where price reacted before. They are not guarantees."),
        "pivots_weekly": raw(p.pivots, "Calculated", lic, safe),
        "risk": raw(dataclasses.asdict(p.risk), "Calculated", lic, safe),
        "returns": raw(p.returns.T.to_dict(), "Calculated", lic, safe),
        "monthly_returns": block(p.monthly.reset_index(), "Calculated", lic, safe),
    })


@app.get("/stocks/{ticker}/earnings", response_model=Envelope, tags=["stocks"],
         summary="EPS actual vs expected, beat rate, post-earnings moves, revisions, upcoming")
def earnings(ticker: str = TickerPath, safe_mode: Optional[bool] = SafeQuery):
    b, safe = get_bundle(ticker), is_safe(safe_mode)
    e = b.earnings
    if e is None:
        raise HTTPException(404, "Earnings data is not available.")
    hist = e.history.drop(columns=["datetime"], errors="ignore")
    sec_cols = ["quarter", "period_end", "eps_gaap", "revenue", "filing_url", "filing_form", "press_release_url"]
    return envelope(b, safe, {
        "history": block(hist, e.estimates_source, DEMO, safe),
        "sec_fields": block(hist[[c for c in sec_cols if c in hist]], "SEC EDGAR", LicenseTag.COMMERCIAL_OK.value, False),
        "beat_rate_8": raw({"rate": e.beat_rate_8[0], "beats": e.beat_rate_8[1], "quarters": e.beat_rate_8[2]},
                           e.estimates_source, DEMO, safe),
        "beat_rate_12": raw({"rate": e.beat_rate_12[0], "beats": e.beat_rate_12[1], "quarters": e.beat_rate_12[2]},
                            e.estimates_source, DEMO, safe),
        "typical_move": raw(e.typical_move, "Calculated", DEMO, safe, note="Average absolute 1-day move after earnings"),
        "upcoming": raw(e.upcoming, "yfinance", DEMO, safe),
        "estimate_revisions": block(e.revisions.reset_index(names="period") if not e.revisions.empty else None,
                                    "yfinance", DEMO, safe),
        "revision_counts": block(e.revision_counts.reset_index(names="period") if not e.revision_counts.empty else None,
                                 "yfinance", DEMO, safe),
        "note": "'eps_reported' is usually the adjusted (non-GAAP) EPS; 'eps_gaap' is the official SEC number.",
    })


@app.get("/stocks/{ticker}/dividends", response_model=Envelope, tags=["stocks"], summary="Dividend summary and history")
def dividends(ticker: str = TickerPath, safe_mode: Optional[bool] = SafeQuery):
    b, safe = get_bundle(ticker), is_safe(safe_mode)
    d = b.dividends
    if d is None:
        raise HTTPException(404, "Dividend data is not available.")
    s = d.summary
    if not s.pays:
        return envelope(b, safe, {"pays_dividend": False, "message": s.reason})
    calc = LicenseTag.CALCULATED_SAFE.value
    return envelope(b, safe, {
        "pays_dividend": True,
        "yield_ttm": raw(s.yield_ttm, "yfinance", DEMO, safe), "dps_ttm": raw(s.dps_ttm, "yfinance", DEMO, safe),
        "frequency_per_year": raw(s.frequency, "yfinance", DEMO, safe),
        "cagr_3y": raw(s.cagr_3y, "yfinance", DEMO, safe), "cagr_5y": raw(s.cagr_5y, "yfinance", DEMO, safe),
        "growth_streak_years": raw(s.streak, "yfinance", DEMO, safe),
        "yield_5y_avg": raw(s.yield_5y_avg, "yfinance", DEMO, safe),
        "next_ex_dividend_date": raw(d.next_ex_date, "yfinance", DEMO, safe),
        "payout_ratio": raw(d.payout_ratio, "Calculated from SEC", calc, safe),
        "fcf_payout": raw(d.fcf_payout, "Calculated from SEC", calc, safe),
        "annual_dps": raw(d.annual.to_dict(), "yfinance", DEMO, safe),
        "history": block(d.dividends.rename("dividend").rename_axis("ex_date").reset_index(), "yfinance", DEMO, safe),
        "sec_declared_dps_by_fiscal_year": raw(d.sec_dps.to_dict(), "SEC EDGAR", LicenseTag.COMMERCIAL_OK.value, safe),
    })


@app.get("/stocks/{ticker}/ownership", response_model=Envelope, tags=["stocks"],
         summary="Holders, insider transactions, Wall Street analysts' ratings, short interest")
def ownership(ticker: str = TickerPath, safe_mode: Optional[bool] = SafeQuery):
    b, safe = get_bundle(ticker), is_safe(safe_mode)
    o = b.ownership
    if o is None:
        raise HTTPException(404, "Ownership data is not available.")
    return envelope(b, safe, {
        "holder_breakdown": raw(o.breakdown, "yfinance", DEMO, safe),
        "top_institutions": block(o.top_institutions, "yfinance", DEMO, safe),
        "insider_transactions": block(o.insiders.head(100), "yfinance", DEMO, safe),
        "insider_monthly_net": block(o.insider_monthly.reset_index(names="month"), "yfinance", DEMO, safe),
        "wall_street_analysts_ratings": {
            **block(o.recommendations, o.rec_source or "yfinance", DEMO, safe),
            "note": "Third-party opinions from Wall Street analysts. Not our view or a recommendation."},
        "analyst_consensus": raw(o.consensus, o.rec_source or "yfinance", DEMO, safe,
                                 note="mean_score: 1 = strong buy ... 5 = strong sell (Wall Street analysts' ratings)"),
        "rating_changes": block(o.upgrades, "yfinance", DEMO, safe),
        "short_interest": raw(o.short, "yfinance", DEMO, safe),
    })


@app.get("/stocks/{ticker}/news", response_model=Envelope, tags=["stocks"], summary="Company news and SEC filings")
def news(ticker: str = TickerPath, safe_mode: Optional[bool] = SafeQuery,
         days: int = Query(30, ge=1, le=30, description="News from the last N days")):
    b, safe = get_bundle(ticker), is_safe(safe_mode)
    n = b.news
    if n is None:
        raise HTTPException(404, "News is not available.")
    cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=days)
    items = [i for i in n.items if (i["datetime"] if i["datetime"].tzinfo else i["datetime"].tz_localize("UTC")) >= cutoff]
    return envelope(b, safe, {
        "news": block(items, n.source or "Finnhub", DEMO, safe),
        "sec_filings": block([f.model_dump() for f in n.filings[:100]], "SEC EDGAR", LicenseTag.COMMERCIAL_OK.value, safe),
    })


@app.get("/stocks/{ticker}/profile", response_model=Envelope, tags=["stocks"], summary="Company profile")
def profile(ticker: str = TickerPath, safe_mode: Optional[bool] = SafeQuery):
    b, safe = get_bundle(ticker), is_safe(safe_mode)
    p = b.header.profile
    fields = ("name", "exchange", "sector", "industry", "sic_code", "sic_description", "description", "employees",
              "headquarters", "website", "ceo", "fiscal_year_end", "ipo_date", "logo_url", "state_of_incorporation", "peers")
    return envelope(b, safe, {"cik": p.cik, "sec_filings_url": p.sec_filings_url,
                              "is_financial_company": p.is_financial_company,
                              **{f: val(getattr(p, f), safe) for f in fields},
                              "shares_outstanding": val(b.header.shares_outstanding, safe)})


_fx: dict[str, tuple[float, dict]] = {}


@app.get("/fx/usdidr", tags=["fx"], summary="US dollar to Indonesian rupiah rate (latest daily close)")
def fx_usdidr(safe_mode: Optional[bool] = SafeQuery):
    """Used by the mobile prototype to show prices in Rupiah. Yahoo Finance data, so DEMO_ONLY."""
    safe = is_safe(safe_mode)
    hit = _fx.get("usdidr")
    if not hit or time.time() - hit[0] > 3600:
        df = registry.yfinance().get_history_raw("IDR=X", period="5d")
        if df is None or df.empty:
            raise HTTPException(503, "USD/IDR rate is not available right now.")
        hit = (time.time(), {"rate": float(df["Close"].dropna().iloc[-1]), "as_of": df.index[-1]})
        _fx["usdidr"] = hit
    return {"pair": "USD/IDR", **raw(hit[1]["rate"], "yfinance", DEMO, safe, as_of=hit[1]["as_of"])}


@app.get("/coverage/{ticker}", response_model=Envelope, tags=["coverage"],
         summary="Data coverage report: every field, its source, license tag and whether it loaded")
def coverage(ticker: str = TickerPath, safe_mode: Optional[bool] = SafeQuery):
    b, safe = get_bundle(ticker), is_safe(safe_mode)
    rows = coverage_rows(b, safe)
    return envelope(b, safe, {"summary": coverage_summary(rows), "fields": rows})
