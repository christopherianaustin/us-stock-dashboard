"""Build the compact data the AI sees for one tab (SPEC 15.4).

Code calculates, AI explains: every number and comparison is prepared here (rounded to 2-3 significant digits,
ratios turned into percentages, money into short units), so the model never has to do math.

Input: the `data` part of our own API answers (api/main.py), keyed by section name, e.g.
    {"summary": {...}, "ratios": {...}, "valuation": {...}}
plus the rule-based pillar scores and insights. The same dicts come from the live API or from the saved files in
mobile-ui/public/mock/, so this module needs no network and is easy to test.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Optional

TABS: tuple[str, ...] = ("summary", "price_technicals", "earnings", "financials", "valuation",
                         "profitability_health", "dividends", "ownership_sentiment", "news_filings", "company_profile")

# API sections each tab needs (names used by the API collector; see api/main.py ai_summary)
TAB_SECTIONS: dict[str, tuple[str, ...]] = {
    "summary": ("summary", "valuation"),
    "price_technicals": ("summary", "technicals"),
    "earnings": ("summary", "earnings"),
    "financials": ("summary", "ratios", "fin_q_income", "fin_q_cashflow", "fin_q_balance", "fin_a_income"),
    "valuation": ("summary", "ratios", "valuation"),
    "profitability_health": ("summary", "ratios", "profile"),
    "dividends": ("summary", "dividends", "ratios"),
    "ownership_sentiment": ("summary", "ownership", "valuation"),
    "news_filings": ("summary", "news"),
    "company_profile": ("summary", "profile"),
}

# Rule-based pillar(s) behind each tab's starting signal (Section 7 scorecard). None = no good-or-bad reading.
TAB_PILLARS: dict[str, Optional[tuple[str, ...]]] = {
    "summary": ("valuation", "growth", "profitability", "financial_health", "earnings_quality", "momentum", "dividend"),
    "price_technicals": ("momentum",),
    "earnings": ("earnings_quality",),
    "financials": ("growth",),
    "valuation": ("valuation",),
    "profitability_health": ("profitability", "financial_health"),
    "dividends": ("dividend",),
    "ownership_sentiment": None,
    "news_filings": None,
    "company_profile": None,
}

LEVEL_SIGNAL = {"strong": "Strong", "neutral": "Neutral", "weak": "Weak", None: "Not enough data",
                "not_applicable": "Not applicable"}
LICENSE_RANK = {"COMMERCIAL_OK": 0, "CALCULATED_SAFE": 1, "MIXED": 2, "DEMO_ONLY": 2}
SCALES_EN = ((1e12, "trillion"), (1e9, "billion"), (1e6, "million"), (1e3, "thousand"))


# =========================================================================== small helpers
def round_sig(x: Any, sig: int = 3) -> Any:
    """Round to `sig` significant digits (2-3 per SPEC 15.4). Whole numbers stay whole; non-numbers pass through."""
    if not isinstance(x, (int, float)) or isinstance(x, bool) or x is None:
        return x
    if isinstance(x, float) and (math.isnan(x) or math.isinf(x)):
        return None
    if x == 0:
        return 0
    r = float(f"{x:.{sig}g}")
    return int(r) if r.is_integer() else r


def display_format(lang: str, currency: str) -> dict:
    """How the model should write money and percentages (SPEC 15.6.2).
    Both languages use comma for thousands and dot for decimals, like the rest of the Nanovest app (decided in 9a)."""
    example = "Rp1,234,567" if currency == "IDR" else "$1,234.56"
    return {"currency": currency, "example": example, "percent example": "12.5%"}


def rule_signal(pillars: dict[str, dict], tab: str) -> str:
    """Starting signal for a tab, from the rule-based pillar levels (Section 7)."""
    keys = TAB_PILLARS[tab]
    if keys is None:
        return "Not applicable"
    found = [pillars.get(k) or {} for k in keys]
    if len(keys) == 1:
        return LEVEL_SIGNAL.get(found[0].get("level"), "Not enough data")
    scores = [p["score"] for p in found if p.get("score") is not None]
    if not scores:
        return "Not applicable" if all(p.get("level") == "not_applicable" for p in found) else "Not enough data"
    avg = sum(scores) / len(scores)
    return "Strong" if avg >= 70 else ("Neutral" if avg >= 40 else "Weak")


@dataclass
class Builder:
    """Collects metrics for one tab, converting units and tracking license tags and missing values."""
    lang: str = "en"
    currency: str = "USD"
    fx: Optional[float] = None          # USD -> IDR, only used when currency == "IDR"
    metrics: list[dict] = field(default_factory=list)
    missing: list[dict] = field(default_factory=list)
    tags: set[str] = field(default_factory=set)

    # ----- unit conversion
    def money_unit(self) -> str:
        return "IDR" if self.currency == "IDR" else "USD"

    def conv(self, v: Any, unit: str) -> tuple[Any, str]:
        """(value, unit) ready for the model: ratios -> %, money -> short units in the display currency."""
        if v is None:
            return None, unit
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            return v, unit
        if unit == "ratio":
            return round_sig(v * 100), "%"
        if unit in ("USD", "USD/shares"):
            m = v * self.fx if self.currency == "IDR" and self.fx else v
            cur = self.money_unit()
            if unit == "USD/shares":
                if cur == "USD":
                    return round(m, 2) if abs(m) < 1000 else round_sig(m, 4), "USD per share"
                return round_sig(m, 4), "IDR per share"
            for div, word in SCALES_EN:
                if abs(m) >= div:
                    return round_sig(m / div), f"{cur} {word}"
            return round_sig(m), cur
        if unit in ("count", "days", "years", "score"):
            return v, unit
        return round_sig(v), unit

    def track(self, tag: Optional[str]) -> None:
        if tag:
            self.tags.add(tag)

    # ----- add one metric
    def add(self, key: str, label: str, val: Optional[dict], unit: str, *, period: Optional[str] = None,
            compare: Optional[dict] = None, note: Optional[str] = None) -> Optional[dict]:
        """`val` is an API value dict ({value, license_tag, na_reason, ...}). Missing values go to `missing`."""
        if not val or val.get("value") is None:
            reason = (val or {}).get("na_reason") or "Not available"
            self.missing.append({"key": key, "label": label, "reason": reason})
            return None
        value, u = self.conv(val["value"], unit)
        m: dict[str, Any] = {"key": key, "label": label, "value": value, "unit": u}
        if period:
            m["period"] = period
        if compare:
            c = {k: v for k, v in compare.items() if v is not None}
            if c:
                m["compare"] = c
        n = note or val.get("note")
        if n and not (self.currency == "IDR" and "$" in n):   # dollar amounts in notes would confuse Rupiah text
            m["note"] = n
        m["license_tag"] = val.get("license_tag")
        self.track(val.get("license_tag"))
        self.metrics.append(m)
        return m

    def cmp(self, v: Any, unit: str) -> Any:
        """Convert a comparison value into the same unit as its metric."""
        return self.conv(v, unit)[0] if v is not None else None

    @property
    def license_tag(self) -> str:
        if not self.tags:
            return "CALCULATED_SAFE"
        worst = max(self.tags, key=lambda t: LICENSE_RANK.get(t, 2))
        return "DEMO_ONLY" if LICENSE_RANK.get(worst, 2) >= 2 else worst


def _v(section: Optional[dict], *path: str) -> Optional[dict]:
    """Walk into an API section; returns the value dict or None."""
    cur: Any = section
    for p in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(p)
    return cur if isinstance(cur, dict) else None


def _raw(value: Any, tag: Optional[str], na: Optional[str] = None) -> dict:
    return {"value": value, "license_tag": tag, "na_reason": na}


def _block_missing(b: Builder, key: str, label: str, block: Optional[dict]) -> bool:
    """True if a list block is usable; otherwise records it as missing."""
    if block and block.get("available") and block.get("items"):
        b.track(block.get("license_tag"))
        return True
    b.missing.append({"key": key, "label": label, "reason": (block or {}).get("na_reason") or "Not available"})
    return False


# =========================================================================== shared parts
def _company(sections: dict) -> dict:
    h = (sections.get("summary") or {}).get("header") or {}
    g = lambda k: (h.get(k) or {}).get("value")  # noqa: E731
    return {"ticker": sections.get("_ticker"), "company": g("name"), "sector": g("sector"), "industry": g("industry"),
            "exchange": g("exchange")}


def _price(b: Builder, sections: dict) -> None:
    h = (sections.get("summary") or {}).get("header") or {}
    b.add("price", "Share price", h.get("price"), "USD/shares")
    if h.get("change_pct"):
        b.add("change_pct_1d", "Price change today", h.get("change_pct"), "ratio")


def _events(sections: dict) -> dict:
    h = (sections.get("summary") or {}).get("header") or {}
    ev = {}
    ne = (h.get("next_earnings_date") or {}).get("value")
    if ne:
        ev["next_earnings_date"] = ne
    return ev


def _insights(insights: list[dict], tab: str) -> tuple[list[str], list[str]]:
    pillars = TAB_PILLARS[tab]
    if pillars is None:
        return [], []
    pick = [i for i in insights if i.get("pillar") in pillars]
    lim = 5 if tab == "summary" else 4
    return ([i["text"] for i in pick if i["kind"] == "strength"][:lim],
            [i["text"] for i in pick if i["kind"] == "risk"][:lim])


def _pct_points(v: Optional[float]) -> Optional[float]:
    return round_sig(v * 100) if isinstance(v, (int, float)) else None


# =========================================================================== tab builders
def _tab_summary(b: Builder, s: dict, out: dict) -> None:
    summ = s.get("summary") or {}
    h = summ.get("header") or {}
    val = s.get("valuation") or {}
    ks = summ.get("key_stats") or {}
    peers = (summ.get("peer_medians") or {}).get("value") or {}
    hs = val.get("history_stats") or {}
    _price(b, s)
    b.add("market_cap", "Market value", h.get("market_cap"), "USD")
    b.add("week52_high", "52-week high", h.get("week52_high"), "USD/shares")
    b.add("week52_low", "52-week low", h.get("week52_low"), "USD/shares")
    peer_key = {"pe": "pe", "ps": "ps", "ev_ebitda": "ev_ebitda", "revenue_yoy": "revenue_growth",
                "net_margin": "net_margin", "roe": "roe"}
    for k, st in ks.items():
        unit = st.get("unit") or "x"
        hist = (hs.get(k) or {}).get("value") or {}
        comp = {"peer_median": b.cmp(peers.get(peer_key.get(k, "")), unit),
                "own_5y_median": b.cmp(hist.get("median"), unit),
                "own_5y_percentile": _pct_points(hist.get("percentile"))}
        b.add(k, st.get("label") or k, st, unit, compare=comp)
    out["pillars"] = [{"pillar": p.get("label"), "level": p.get("level_label"), "score": p.get("score"),
                       "metrics_used": f'{p.get("metrics_used")} of {p.get("metrics_total")}'}
                      for p in summ.get("scorecard") or []]


def _tab_valuation(b: Builder, s: dict, out: dict) -> None:
    summ, rat, val = s.get("summary") or {}, s.get("ratios") or {}, s.get("valuation") or {}
    h = summ.get("header") or {}
    hs = val.get("history_stats") or {}
    pm_v = val.get("peer_medians") or {}
    peers = pm_v.get("value") or {}
    if peers:
        b.track(pm_v.get("license_tag"))
    _price(b, s)
    b.add("market_cap", "Market value", h.get("market_cap"), "USD")
    for k in ("pe", "forward_pe", "peg", "ps", "pb", "ev_ebitda", "p_fcf", "fcf_yield", "earnings_yield"):
        r = rat.get(k)
        if r is None:
            continue
        unit = r.get("unit") or "x"
        hv = hs.get(k) or {}
        hist = hv.get("value") or {}
        if hist:
            b.track(hv.get("license_tag"))
        comp = {"own_5y_median": b.cmp(hist.get("median"), unit), "own_5y_low": b.cmp(hist.get("low"), unit),
                "own_5y_high": b.cmp(hist.get("high"), unit),
                "own_5y_percentile": _pct_points(hist.get("percentile")),
                "peer_median": b.cmp(peers.get(k), unit)}
        b.add(k, r.get("label") or k, r, unit, compare=comp, period="TTM" if "TTM" in (r.get("label") or "") else None)
    # growth helps explain the price
    for k in ("revenue_yoy", "eps_yoy", "revenue_cagr_3y", "eps_cagr_3y"):
        r = rat.get(k)
        if r is None:
            continue
        comp = {"peer_median": b.cmp(peers.get("revenue_growth"), "ratio")} if k == "revenue_yoy" else None
        b.add(k, r.get("label") or k, r, "ratio", compare=comp)
    # fair value estimates (all are estimates based on assumptions)
    fv: dict[str, Any] = {"note": "Estimates based on assumptions, not predictions."}
    g = val.get("graham_number")
    if g and g.get("value") is not None:
        b.add("graham_number", "Graham number (classic fair value formula, estimate)", g, "USD/shares")
    dcf = val.get("dcf") or {}
    sc = dcf.get("scenarios") or {}
    for name in ("Bear", "Base", "Bull"):
        if name in sc:
            b.add(f"dcf_{name.lower()}", f"DCF value per share, {name.lower()} case (estimate)", sc[name], "USD/shares")
    if not sc:
        b.missing.append({"key": "dcf", "label": "DCF estimate", "reason": dcf.get("na_reason") or "Not available"})
    a = dcf.get("assumptions")
    if a:
        fv["dcf_assumptions"] = {"cash_flow_growth_per_year_pct": _pct_points(a.get("growth")),
                                 "growth_source": a.get("growth_source"),
                                 "discount_rate_pct": _pct_points(a.get("discount_rate")),
                                 "long_term_growth_pct": _pct_points(a.get("terminal_growth"))}
    t = val.get("analyst_targets") or {}
    tv = t.get("value")
    if tv:
        for k in ("low", "mean", "high"):
            b.add(f"analyst_target_{k}", f"Wall Street analysts' price target, {k}", _raw(tv.get(k), t.get("license_tag")),
                  "USD/shares", note="Third-party estimate by Wall Street analysts")
    else:
        b.missing.append({"key": "analyst_targets", "label": "Analyst price targets", "reason": t.get("na_reason") or "Not available"})
    out["fair_value_notes"] = fv


def _tab_price(b: Builder, s: dict, out: dict) -> None:
    t = s.get("technicals") or {}
    snap_v = t.get("snapshot") or {}
    snap = snap_v.get("value") or {}
    tag = snap_v.get("license_tag")
    _price(b, s)
    if snap:
        p = snap.get("price")
        for k, label in (("sma50", "50-day average price"), ("sma200", "200-day average price")):
            if snap.get(k):
                b.add(k, label, _raw(snap[k], tag), "USD/shares",
                      compare={"price_vs_average_pct": round_sig((p / snap[k] - 1) * 100) if p else None})
        b.add("rsi14", "RSI 14 days (0-100; above 70 = rose fast, below 30 = fell fast)", _raw(round_sig(snap.get("rsi14")), tag), "index")
        b.add("from_high_52w", "Distance from 52-week high", _raw(snap.get("from_high_52w"), tag), "ratio")
        b.add("from_low_52w", "Distance from 52-week low", _raw(snap.get("from_low_52w"), tag), "ratio")
    else:
        b.missing.append({"key": "snapshot", "label": "Price indicators", "reason": snap_v.get("na_reason") or "Not available"})
    rv = t.get("returns") or {}
    ret = rv.get("value") or {}
    if ret:
        b.track(rv.get("license_tag"))
        names = list((ret.get("1Y") or next(iter(ret.values()))).keys())
        stock = names[0]
        sector = next((n for n in names if n not in (stock, "SPY")), None)
        out["returns_pct"] = [{"period": per, "stock": _pct_points(r.get(stock)), "sp500": _pct_points(r.get("SPY")),
                               **({f"sector_etf_{sector}": _pct_points(r.get(sector))} if sector else {})}
                              for per, r in ret.items() if per in ("1M", "3M", "6M", "YTD", "1Y", "3Y", "5Y")]
    else:
        b.missing.append({"key": "returns", "label": "Returns vs S&P 500", "reason": rv.get("na_reason") or "Not available"})
    risk_v = t.get("risk") or {}
    risk = risk_v.get("value") or {}
    for k, label, unit in (("beta", "Beta (how much it moves vs the market; 1 = same)", "x"),
                           ("volatility_1y", "Volatility, 1 year (typical yearly swing)", "ratio"),
                           ("max_drawdown_1y", "Biggest drop from a peak, 1 year", "ratio"),
                           ("max_drawdown_5y", "Biggest drop from a peak, 5 years", "ratio"),
                           ("current_drawdown", "Current distance below the last peak", "ratio"),
                           ("sharpe_1y", "Sharpe ratio, 1 year (return per unit of risk)", "x")):
        b.add(k, label, _raw(risk.get(k), risk_v.get("license_tag"), risk_v.get("na_reason")), unit)
    srv = t.get("support_resistance") or {}
    sr = srv.get("value") or {}
    if sr:
        b.track(srv.get("license_tag"))
        lv = lambda x: {"price": b.cmp(x["price"], "USD/shares"), "distance_from_price_pct": _pct_points(x["distance"]),  # noqa: E731
                        "times_touched": x.get("touches")}
        out["nearest_support"] = [lv(x) for x in sorted(sr.get("supports") or [], key=lambda x: abs(x["distance"]))[:2]]
        out["nearest_resistance"] = [lv(x) for x in sorted(sr.get("resistances") or [], key=lambda x: abs(x["distance"]))[:2]]
        out["support_resistance_note"] = "Areas where the price reacted before. Not guarantees."
    sig = t.get("signals") or {}
    if _block_missing(b, "signals", "Technical signals", sig):
        out["recent_signals"] = [{"fact": x.get("fact"), "date": x.get("date")} for x in sig["items"][-6:]]


def _tab_earnings(b: Builder, s: dict, out: dict) -> None:
    e = s.get("earnings") or {}
    br = (e.get("beat_rate_8") or {})
    if br.get("value"):
        bv = br["value"]
        b.add("beat_rate_8q", "Quarters with EPS above estimates (last 8)",
              _raw(f'{bv.get("beats")} of {bv.get("quarters")}', br.get("license_tag")), "quarters")
    else:
        b.missing.append({"key": "beat_rate_8q", "label": "Beat rate", "reason": br.get("na_reason") or "Not available"})
    b.add("typical_move", "Typical 1-day price move after earnings (up or down)", e.get("typical_move"), "ratio")
    hist = e.get("history") or {}
    if _block_missing(b, "history", "Earnings history", hist):
        rows = [r for r in hist["items"] if r.get("eps_reported") is not None][-8:]
        out["last_quarters"] = [{
            "quarter": r.get("quarter"), "date": r.get("date"),
            "eps_estimate": b.cmp(r.get("eps_estimate"), "USD/shares"), "eps_actual": b.cmp(r.get("eps_reported"), "USD/shares"),
            "surprise_pct": round_sig(r.get("surprise_pct")), "result": r.get("result"),
            "price_move_next_day_pct": _pct_points(r.get("move_1d"))} for r in rows]
        out["eps_note"] = "EPS = earnings per share (usually adjusted). Estimates are Wall Street analysts' averages."
    up = (e.get("upcoming") or {})
    if up.get("value"):
        u = up["value"]
        b.track(up.get("license_tag"))
        out["next_earnings"] = {"date": u.get("date"), "timing": u.get("timing"), "days_from_today": u.get("days"),
                                "analysts_eps_estimate": b.cmp(u.get("eps_estimate"), "USD/shares"),
                                "eps_a_year_ago": b.cmp(u.get("year_ago_eps"), "USD/shares"),
                                "analysts_revenue_estimate": b.conv(u.get("revenue_estimate"), "USD") if u.get("revenue_estimate") else None,
                                "analysts_count": u.get("analysts")}
    else:
        b.missing.append({"key": "next_earnings", "label": "Next earnings date", "reason": up.get("na_reason") or "Not announced"})
    rc = e.get("revision_counts") or {}
    if rc.get("available") and rc.get("items"):
        b.track(rc.get("license_tag"))
        out["analyst_estimate_revisions_30d"] = [{"period": r.get("period"), "raised": r.get("Up (30 days)"),
                                                  "cut": r.get("Down (30 days)")} for r in rc["items"]]


def _tab_financials(b: Builder, s: dict, out: dict) -> None:
    q_fields = {"revenue": "Revenue", "net_income": "Net income", "gross_margin": "Gross margin",
                "operating_margin": "Operating margin", "net_margin": "Net margin", "revenue_yoy": "Revenue vs same quarter last year"}
    # money in one fixed scale per table so rows compare directly
    q = _money_table(b, s.get("fin_q_income"), q_fields, 8)
    if q[0]:
        out["quarterly_income"] = {"columns": q[1], "rows": q[0]}
    else:
        b.missing.append({"key": "quarterly_income", "label": "Quarterly income statement", "reason": "Not available"})
    cf = _money_table(b, s.get("fin_q_cashflow"), {"operating_cash_flow": "Operating cash flow", "capex": "Capital spending",
                                                   "fcf": "Free cash flow"}, 8)
    if cf[0]:
        out["quarterly_cash_flow"] = {"columns": cf[1], "rows": cf[0]}
    bal = _money_table(b, s.get("fin_q_balance"), {"cash": "Cash", "total_debt": "Total debt", "net_debt": "Net debt"}, 4)
    if bal[0]:
        out["balance_sheet"] = {"columns": bal[1], "rows": bal[0]}
    yr = _money_table(b, s.get("fin_a_income"), {"revenue": "Revenue", "net_income": "Net income", "net_margin": "Net margin"}, 4)
    if yr[0]:
        out["annual"] = {"columns": yr[1], "rows": yr[0]}
    for sec_name in ("fin_q_income", "fin_q_cashflow", "fin_q_balance"):
        for f, reason in ((s.get(sec_name) or {}).get("not_available") or {}).items():
            if f in q_fields or f in ("fcf", "operating_cash_flow", "cash", "total_debt", "net_debt"):
                b.missing.append({"key": f, "label": f.replace("_", " "), "reason": reason})
    rat = s.get("ratios") or {}
    for k in ("revenue_yoy", "eps_yoy", "revenue_cagr_3y", "cash_conversion"):
        if rat.get(k):
            b.add(k, rat[k].get("label") or k, rat[k], rat[k].get("unit") or "ratio")


def _money_table(b: Builder, sec: Optional[dict], fields: dict[str, str], n: int) -> tuple[list[dict], dict]:
    """Last `n` periods as rows. Every money column uses one scale (the scale of its largest value)."""
    if not sec or not sec.get("rows"):
        return [], {}
    rows = sec["rows"]
    b.track(rows[0].get("license_tag"))
    periods = (sec.get("periods") or [])[-n:]
    fx = b.fx if b.currency == "IDR" and b.fx else 1.0
    cur = b.money_unit()
    table: list[dict] = [{"period": p["label"]} for p in periods]
    columns: dict[str, dict] = {}
    for f, label in fields.items():
        cells = [next((x for x in rows if x["field"] == f and x["period_end"] == p["period_end"]), None) for p in periods]
        vals = [c["value"] for c in cells if c and c.get("value") is not None]
        if not vals:
            continue
        unit = next(c.get("unit") for c in cells if c)
        if unit == "ratio":
            for r, c in zip(table, cells):
                if c and c.get("value") is not None:
                    r[f] = round_sig(c["value"] * 100)
            columns[f] = {"label": label, "unit": "%"}
        else:
            big = max(abs(v) for v in vals) * fx
            div, word = next(((d, w) for d, w in SCALES_EN if big >= d), (1, ""))
            for r, c in zip(table, cells):
                if c and c.get("value") is not None:
                    r[f] = round_sig(c["value"] * fx / div)
            columns[f] = {"label": label, "unit": f"{cur} {word}".strip()}
    return table, columns


def _tab_prof_health(b: Builder, s: dict, out: dict) -> None:
    rat = s.get("ratios") or {}
    peers = ((s.get("summary") or {}).get("peer_medians") or {}).get("value") or {}
    for k in ("roe", "roa", "roic", "gross_margin", "operating_margin", "net_margin", "asset_turnover", "equity_multiplier"):
        if k in rat:
            unit = rat[k].get("unit") or "ratio"
            comp = {"peer_median": b.cmp(peers.get(k), unit)} if k in ("roe", "net_margin") else None
            b.add(k, rat[k].get("label") or k, rat[k], unit, compare=comp)
    for k in ("debt_to_equity", "net_debt", "current_ratio", "quick_ratio", "debt_to_ebitda", "interest_coverage"):
        if k in rat:
            b.add(k, rat[k].get("label") or k, rat[k], rat[k].get("unit") or "x")
    pio = rat.get("piotroski") or {}
    if pio.get("value") is not None:
        b.add("piotroski", "Piotroski score (0-9 checks of financial strength passed)",
              _raw(f'{pio["value"]} of {pio.get("tests_run")}', pio.get("license_tag")), "checks")
        out["piotroski_checks"] = [{"check": c.get("name"), "passed": c.get("passed"), "detail": c.get("detail")}
                                   for c in pio.get("checks") or []]
    else:
        b.missing.append({"key": "piotroski", "label": "Piotroski score", "reason": pio.get("na_reason") or "Not available"})
    alt = rat.get("altman_z") or {}
    m = b.add("altman_z", "Altman Z-score (bankruptcy-risk score: below 1.8 distress, 1.8-3 grey zone, above 3 safe)",
              alt, "score", note=None)
    if m and alt.get("zone"):
        m["zone"] = alt["zone"]
    prof = s.get("profile") or {}
    if prof.get("is_financial_company"):
        out["note"] = "This is a bank or financial company: debt ratios and gross margin work differently and may not apply."


def _tab_dividends(b: Builder, s: dict, out: dict) -> None:
    d = s.get("dividends") or {}
    if not d.get("pays_dividend"):
        out["pays_dividend"] = False
        out["dividend_note"] = d.get("message") or "The company does not pay a dividend."
        rat = s.get("ratios") or {}
        if rat.get("shareholder_returns", {}).get("value") is not None:
            b.add("shareholder_returns", rat["shareholder_returns"].get("label") or "Shareholder returns",
                  rat["shareholder_returns"], rat["shareholder_returns"].get("unit") or "ratio")
        return
    out["pays_dividend"] = True
    yv = d.get("yield_5y_avg") or {}
    b.add("yield_ttm", "Dividend yield (last 12 months)", d.get("yield_ttm"), "ratio",
          compare={"own_5y_average": b.cmp(yv.get("value"), "ratio")})
    b.add("dps_ttm", "Dividend per share (last 12 months)", d.get("dps_ttm"), "USD/shares")
    b.add("frequency_per_year", "Payments per year", d.get("frequency_per_year"), "count")
    b.add("cagr_3y", "Dividend growth per year, 3 years", d.get("cagr_3y"), "ratio")
    b.add("cagr_5y", "Dividend growth per year, 5 years", d.get("cagr_5y"), "ratio")
    b.add("growth_streak_years", "Years in a row with a higher dividend", d.get("growth_streak_years"), "years")
    b.add("payout_ratio", "Share of profit paid as dividends", d.get("payout_ratio"), "ratio")
    b.add("fcf_payout", "Share of free cash flow paid as dividends", d.get("fcf_payout"), "ratio")
    nx = d.get("next_ex_dividend_date") or {}
    if nx.get("value"):
        out["next_ex_dividend_date"] = nx["value"]
        b.track(nx.get("license_tag"))
    ad = (d.get("annual_dps") or {})
    if ad.get("value"):
        b.track(ad.get("license_tag"))
        out["dividend_per_share_by_year"] = {y: b.cmp(v, "USD/shares") for y, v in list(ad["value"].items())[-6:]}


def _tab_ownership(b: Builder, s: dict, out: dict) -> None:
    o, val = s.get("ownership") or {}, s.get("valuation") or {}
    c = o.get("analyst_consensus") or {}
    cv = c.get("value")
    if cv:
        b.track(c.get("license_tag"))
        cnt = cv.get("counts") or {}
        out["wall_street_analyst_ratings"] = {
            "note": "Third-party opinions from Wall Street analysts, not our view.",
            "month": cv.get("month"), "analysts": cv.get("total"),
            "strong_buy": cnt.get("strongBuy"), "buy": cnt.get("buy"), "hold": cnt.get("hold"),
            "sell": cnt.get("sell"), "strong_sell": cnt.get("strongSell"),
            "average_score_1_strong_buy_to_5_strong_sell": round_sig(cv.get("mean_score"))}
    else:
        b.missing.append({"key": "analyst_ratings", "label": "Analyst ratings", "reason": c.get("na_reason") or "Not available"})
    _price(b, s)
    t = val.get("analyst_targets") or {}
    if t.get("value"):
        for k in ("low", "mean", "high"):
            b.add(f"analyst_target_{k}", f"Wall Street analysts' 12-month price target, {k}",
                  _raw(t["value"].get(k), t.get("license_tag")), "USD/shares")
    ch = o.get("rating_changes") or {}
    if ch.get("available") and ch.get("items"):
        b.track(ch.get("license_tag"))
        out["recent_rating_changes_by_analysts"] = [{k: r.get(k) for k in ("date", "firm", "action", "from", "to")}
                                                    for r in ch["items"][:6]]
    hb = o.get("holder_breakdown") or {}
    if hb.get("value"):
        b.track(hb.get("license_tag"))
        out["who_owns_the_shares_pct"] = {k: _pct_points(v) for k, v in hb["value"].items()}
    ti = o.get("top_institutions") or {}
    if ti.get("available") and ti.get("items"):
        out["top_institutions"] = [{"holder": r.get("holder"), "pct_of_shares": _pct_points(r.get("% of shares"))}
                                   for r in ti["items"][:5]]
    im = o.get("insider_monthly_net") or {}
    if im.get("available") and im.get("items"):
        b.track(im.get("license_tag"))
        rows = im["items"][-6:]
        out["insider_net_buying_by_month"] = {
            "unit": b.conv(max((abs(r.get("net") or 0) for r in rows), default=0) or 1, "USD")[1],
            "note": "Positive = insiders bought more than they sold; negative = sold more.",
            "months": [{"month": str(r.get("month"))[:7], "net": b.cmp(r.get("net") or 0, "USD")} for r in rows]}
    else:
        b.missing.append({"key": "insider_trades", "label": "Insider trades", "reason": im.get("na_reason") or "No insider trades"})
    sh = o.get("short_interest") or {}
    if sh.get("value"):
        b.track(sh.get("license_tag"))
        out["short_interest"] = {"pct_of_float_sold_short": _pct_points(sh["value"].get("pct_float")),
                                 "days_to_cover": round_sig(sh["value"].get("days_to_cover")), "as_of": sh["value"].get("as_of")}


FORM_TEXT = {"10-K": "Annual report", "10-Q": "Quarterly report", "8-K": "Company news (current report)",
             "4": "Insider trade", "3": "New insider", "DEF 14A": "Shareholder meeting", "SC 13G": "Large shareholder",
             "SC 13G/A": "Large shareholder", "144": "Planned insider sale", "S-8": "Employee share plan"}


def _tab_news(b: Builder, s: dict, out: dict) -> None:
    n = s.get("news") or {}
    news = n.get("news") or {}
    if _block_missing(b, "news", "News headlines", news):
        out["headlines"] = [{"headline": x.get("headline"), "source": x.get("source"), "date": str(x.get("datetime"))[:10]}
                            for x in news["items"][:15]]
    fil = n.get("sec_filings") or {}
    if _block_missing(b, "sec_filings", "SEC filings", fil):
        out["sec_filings"] = [{"form": f.get("form"), "date": f.get("filing_date"),
                               "what": ("Earnings results" if f.get("form") == "8-K" and "2.02" in (f.get("items") or "")
                                        else FORM_TEXT.get(f.get("form"), f.get("description")))}
                              for f in fil["items"][:10]]


def _tab_profile(b: Builder, s: dict, out: dict) -> None:
    p = s.get("profile") or {}
    h = (s.get("summary") or {}).get("header") or {}
    for k, label in (("description", "Business description"), ("employees", "Employees"), ("headquarters", "Headquarters"),
                     ("ceo", "CEO"), ("ipo_date", "IPO date"), ("fiscal_year_end", "Fiscal year end"),
                     ("sic_description", "Official industry code")):
        v = p.get(k) or {}
        if v.get("value") is not None:
            out[k] = v["value"]
            b.track(v.get("license_tag"))
        else:
            b.missing.append({"key": k, "label": label, "reason": v.get("na_reason") or "Not available"})
    b.add("market_cap", "Market value", h.get("market_cap"), "USD")
    peers = (p.get("peers") or {}).get("value")
    if peers:
        out["similar_companies"] = peers[:8]


BUILDERS = {"summary": _tab_summary, "valuation": _tab_valuation, "price_technicals": _tab_price,
            "earnings": _tab_earnings, "financials": _tab_financials, "profitability_health": _tab_prof_health,
            "dividends": _tab_dividends, "ownership_sentiment": _tab_ownership, "news_filings": _tab_news,
            "company_profile": _tab_profile}


# =========================================================================== public
@dataclass
class TabInput:
    tab: str
    payload: dict            # the JSON inside <stock_data>
    rule_signal: str         # starting signal (Section 7)
    license_tag: str         # worst license tag of the inputs
    strengths: list[str]     # rule-based, used for the fallback
    risks: list[str]


def build_tab_input(tab: str, sections: dict[str, Any], *, ticker: str, pillars: dict[str, dict],
                    insights: list[dict], lang: str = "en", currency: str = "USD", fx: Optional[float] = None,
                    fx_tag: Optional[str] = None) -> TabInput:
    """Compact data for one tab.

    sections  API `data` dicts by name (see TAB_SECTIONS)
    pillars   {"valuation": {"score": 7, "level": "weak"}, ...}  (rule-based, Section 7)
    insights  [{"kind": "strength"|"risk", "pillar": "valuation", "text": "..."}, ...]  (rule-based)
    """
    if tab not in BUILDERS:
        raise ValueError(f"Unknown tab: {tab}")
    if currency == "IDR" and not fx:
        currency = "USD"   # no rate available (e.g. production-safe mode): stay in dollars
    b = Builder(lang=lang, currency=currency, fx=fx)
    if currency == "IDR":
        b.track(fx_tag or "DEMO_ONLY")
    s = {**sections, "_ticker": ticker}
    out: dict[str, Any] = {}
    BUILDERS[tab](b, s, out)
    strengths, risks = _insights(insights, tab)
    sig = rule_signal(pillars, tab)
    payload: dict[str, Any] = {**_company(s), "tab": tab}
    if TAB_PILLARS[tab] and tab != "summary":
        payload["rule_based_pillars"] = {k: {"score": (pillars.get(k) or {}).get("score"),
                                             "level": LEVEL_SIGNAL.get((pillars.get(k) or {}).get("level"))}
                                         for k in TAB_PILLARS[tab]}
    payload["metrics"] = b.metrics
    payload.update(out)
    if strengths:
        payload["rule_based_strengths"] = strengths
    if risks:
        payload["rule_based_risks"] = risks
    ev = _events(s)
    if ev and tab not in ("company_profile",):
        payload["upcoming_events"] = ev
    if currency == "IDR":
        payload["exchange_rate_used"] = {"usd_idr": round_sig(fx, 5), "note": "Money converted from US dollars by us."}
    gen = (sections.get("summary") or {}).get("_generated_at")
    payload["as_of"] = gen or None
    # drop duplicate "missing" entries
    seen, miss = set(), []
    for m in b.missing:
        if m["key"] not in seen:
            seen.add(m["key"])
            miss.append(m)
    payload["missing"] = miss
    payload = _strip_none(payload)
    return TabInput(tab, payload, sig, b.license_tag, strengths, risks)


def _strip_none(x: Any) -> Any:
    if isinstance(x, dict):
        return {k: _strip_none(v) for k, v in x.items() if v is not None and v != [] and v != {}}
    if isinstance(x, list):
        return [_strip_none(v) for v in x]
    return x
