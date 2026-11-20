"""Ratios: income, balance sheet, cash flow, valuation, profitability (SPEC 6.1 - 6.5).

Two layers:
  * small pure formula functions (easy to unit test, reusable by Nanovest's app)
  * `quarterly_metrics(fin)`: one row per quarter with TTM sums, averages and ratios,
    used for the current snapshot and for trend charts (ROE over time, etc.)
TTM = sum of last 4 quarters; balance sheet = latest quarter; average = (start + end of the TTM period) / 2.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

from core.financials import Financials, wide
from core.models import DataPoint, LicenseTag, Source, combined_license

DEFAULT_TAX_RATE = 0.21  # US federal rate, used when pretax income is not positive


# =========================================================================== formulas
def _ok(x) -> bool:
    return x is not None and not (isinstance(x, float) and math.isnan(x))


def safe_div(a, b) -> Optional[float]:
    if not _ok(a) or not _ok(b) or b == 0:
        return None
    return float(a) / float(b)


def cagr(first, last, years: float) -> Optional[float]:
    """Compound annual growth rate. N/A if either end is zero/negative (growth is undefined)."""
    if not _ok(first) or not _ok(last) or first <= 0 or last <= 0 or years <= 0:
        return None
    return (last / first) ** (1 / years) - 1


def pe_ratio(price, eps) -> tuple[Optional[float], Optional[str]]:
    """P/E = price / EPS. Negative or zero earnings -> N/A (a negative P/E is meaningless)."""
    if not _ok(price) or not _ok(eps):
        return None, "Needs price and earnings per share"
    if eps <= 0:
        return None, "N/A (negative earnings)"
    return price / eps, None


def positive_div(a, b, reason: str) -> tuple[Optional[float], Optional[str]]:
    """a / b only when b > 0 (e.g. EV/EBITDA, P/B); otherwise N/A with reason."""
    if not _ok(a) or not _ok(b):
        return None, "Missing input data"
    if b <= 0:
        return None, reason
    return a / b, None


def enterprise_value(market_cap, total_debt, cash_and_sti) -> Optional[float]:
    if not _ok(market_cap):
        return None
    return market_cap + (total_debt if _ok(total_debt) else 0) - (cash_and_sti if _ok(cash_and_sti) else 0)


def graham_number(eps, bvps) -> tuple[Optional[float], Optional[str]]:
    """sqrt(22.5 x EPS x book value per share) - only if both are positive."""
    if not _ok(eps) or not _ok(bvps):
        return None, "Needs EPS and book value per share"
    if eps <= 0 or bvps <= 0:
        return None, "Only defined when EPS and book value are both positive"
    return math.sqrt(22.5 * eps * bvps), None


def effective_tax_rate(tax, pretax) -> float:
    r = safe_div(tax, pretax) if _ok(pretax) and pretax > 0 else None
    return DEFAULT_TAX_RATE if r is None else min(max(r, 0.0), 0.5)


def roic(operating_income, tax_rate, total_debt, equity, cash_and_sti) -> Optional[float]:
    """ROIC = NOPAT / (debt + equity - cash); NOPAT = operating income x (1 - tax rate)."""
    if not _ok(operating_income) or not _ok(equity):
        return None
    invested = (total_debt if _ok(total_debt) else 0) + equity - (cash_and_sti if _ok(cash_and_sti) else 0)
    if invested <= 0:
        return None
    return operating_income * (1 - tax_rate) / invested


def dupont(net_income, revenue, avg_assets, avg_equity) -> Optional[dict]:
    """ROE = net margin x asset turnover x equity multiplier."""
    nm, at, em = safe_div(net_income, revenue), safe_div(revenue, avg_assets), safe_div(avg_assets, avg_equity)
    if None in (nm, at, em) or avg_equity <= 0:
        return None
    return {"net_margin": nm, "asset_turnover": at, "equity_multiplier": em, "roe": nm * at * em}


# =========================================================================== splits
def split_factor_after(when: pd.Timestamp, splits: Optional[pd.Series]) -> float:
    """Product of split ratios that happened AFTER `when` (e.g. NVDA 10:1 in 2024)."""
    if splits is None or len(splits) == 0 or when is None or pd.isna(when):
        return 1.0
    later = splits[(splits.index > pd.Timestamp(when)) & (splits.index <= pd.Timestamp.today())]
    return float(np.prod(later.values)) if len(later) else 1.0


def split_adjust(values: pd.Series, filed: pd.Series, splits: Optional[pd.Series], per_share: bool) -> pd.Series:
    """Make per-share values (EPS) and share counts comparable with today's split-adjusted prices.
    A value filed before a split is in old shares: EPS / factor, shares x factor."""
    if splits is None or len(splits) == 0:
        return values
    factors = pd.Series([split_factor_after(filed.get(i), splits) for i in values.index], index=values.index)
    return values / factors if per_share else values * factors


# =========================================================================== quarterly table
FLOW_FIELDS = ["revenue", "net_income", "operating_income", "ebitda", "operating_cash_flow", "capex", "fcf",
               "income_tax", "pretax_income", "interest_expense", "eps_diluted", "dividends_paid", "buybacks",
               "da", "gross_profit"]
LEVEL_FIELDS = ["equity", "total_assets", "total_debt", "cash", "short_term_investments", "current_assets",
                "current_liabilities", "inventory", "retained_earnings", "total_liabilities", "long_term_debt",
                "shares_outstanding", "diluted_shares"]


def _per_quarter_filed(fin: Financials, field: str) -> pd.Series:
    r = fin.rows(field, "Q")
    return r["filed"] if "filed" in r else pd.Series(dtype="datetime64[ns]")


def quarterly_metrics(fin: Financials, splits: Optional[pd.Series] = None) -> pd.DataFrame:
    """One row per quarter end with TTM values, balance-sheet levels and ratios."""
    w = wide(fin.tidy, "Q")
    if w.empty:
        return w
    q = w.reindex(columns=sorted(set(FLOW_FIELDS + LEVEL_FIELDS) | set(w.columns))).copy()

    # Split-adjust EPS and share counts so they match today's (split-adjusted) prices
    if splits is not None and len(splits):
        if q["eps_diluted"].notna().any():
            q["eps_diluted"] = split_adjust(q["eps_diluted"], _per_quarter_filed(fin, "eps_diluted"), splits, True)
        for f in ("diluted_shares", "shares_outstanding"):
            if q[f].notna().any():
                q[f] = split_adjust(q[f], _per_quarter_filed(fin, f), splits, False)

    ends = pd.Series(q.index, index=q.index)
    consecutive4 = (ends - ends.shift(3)).dt.days.between(250, 290)   # last 4 rows are 4 straight quarters
    year_back = (ends - ends.shift(4)).dt.days.between(350, 380)      # row 4 back is one year earlier

    for f in FLOW_FIELDS:
        q[f"{f}_ttm"] = q[f].rolling(4, min_periods=4).sum().where(consecutive4)

    def avg(f):
        return ((q[f] + q[f].shift(4)) / 2).where(year_back)

    q["avg_equity"] = avg("equity")
    q["avg_assets"] = avg("total_assets")
    q["cash_sti"] = q["cash"].fillna(0) + q["short_term_investments"].fillna(0)
    q.loc[q["cash"].isna() & q["short_term_investments"].isna(), "cash_sti"] = np.nan
    q["net_debt"] = q["total_debt"].fillna(0) - q["cash_sti"].fillna(0)
    q.loc[q["total_debt"].isna() & q["cash_sti"].isna(), "net_debt"] = np.nan
    q["shares"] = q["shares_outstanding"].combine_first(q["diluted_shares"])

    pos = lambda s: s.where(s > 0)  # noqa: E731
    q["roe"] = q["net_income_ttm"] / pos(q["avg_equity"])
    q["roa"] = q["net_income_ttm"] / pos(q["avg_assets"])
    tax = (q["income_tax_ttm"] / pos(q["pretax_income_ttm"])).clip(0, 0.5).fillna(DEFAULT_TAX_RATE)
    q["eff_tax_ttm"] = tax
    invested = q["total_debt"].fillna(0) + q["equity"] - q["cash_sti"].fillna(0)
    q["roic"] = q["operating_income_ttm"] * (1 - tax) / pos(invested)
    q["net_margin_ttm"] = q["net_income_ttm"] / pos(q["revenue_ttm"])
    q["gross_margin_ttm"] = q["gross_profit_ttm"] / pos(q["revenue_ttm"])
    q["operating_margin_ttm"] = q["operating_income_ttm"] / pos(q["revenue_ttm"])
    q["ebitda_margin_ttm"] = q["ebitda_ttm"] / pos(q["revenue_ttm"])
    q["fcf_margin_ttm"] = q["fcf_ttm"] / pos(q["revenue_ttm"])
    q["asset_turnover"] = q["revenue_ttm"] / pos(q["avg_assets"])
    q["equity_multiplier"] = q["avg_assets"] / pos(q["avg_equity"])
    q["interest_coverage"] = q["operating_income_ttm"] / pos(q["interest_expense_ttm"])
    q["debt_to_ebitda"] = q["total_debt"] / pos(q["ebitda_ttm"])
    q["current_ratio"] = q["current_assets"] / pos(q["current_liabilities"])
    q["quick_ratio"] = (q["current_assets"] - q["inventory"].fillna(0)) / pos(q["current_liabilities"])
    q["debt_to_equity"] = q["total_debt"] / pos(q["equity"])
    q["cash_conversion"] = q["operating_cash_flow_ttm"] / pos(q["net_income_ttm"])
    q["shareholder_returns_ttm"] = q["dividends_paid_ttm"].fillna(0) + q["buybacks_ttm"].fillna(0)
    q.loc[q["dividends_paid_ttm"].isna() & q["buybacks_ttm"].isna(), "shareholder_returns_ttm"] = np.nan
    q["bvps"] = q["equity"] / pos(q["shares"])
    q["fcf_per_share"] = q["fcf_ttm"] / pos(q["shares"])

    # When was this quarter's TTM data public? (filing date of the quarter, earliest version)
    known = []
    for f in ("revenue", "net_income", "eps_diluted"):
        r = fin.rows(f, "Q")
        if "first_filed" in r:
            known.append(r["first_filed"])
    if known:
        q["known_date"] = pd.concat(known, axis=1, sort=True).max(axis=1).reindex(q.index)
    else:
        q["known_date"] = pd.NaT
    return q


def annual_series(fin: Financials, field: str, splits: Optional[pd.Series] = None) -> pd.Series:
    """FY values indexed by fiscal year (split-adjusted for EPS)."""
    r = fin.rows(field, "FY")
    if r.empty:
        return pd.Series(dtype=float)
    vals = r["value"]
    if field == "eps_diluted" and splits is not None:
        vals = split_adjust(vals, r["filed"], splits, per_share=True)
    return pd.Series(vals.values, index=r["fiscal_year"].astype(int).values).groupby(level=0).last().sort_index()


def cagr_from_annual(s: pd.Series, years: int) -> tuple[Optional[float], Optional[str]]:
    if s.empty:
        return None, "Not reported"
    last_fy = s.index.max()
    if last_fy - years not in s.index:
        return None, f"Needs {years + 1} years of data"
    v = cagr(s[last_fy - years], s[last_fy], years)
    if v is None:
        return None, "N/A (a starting or ending value is zero or negative)"
    return v, None


# =========================================================================== snapshot
@dataclass
class MarketInputs:
    price: Optional[float]
    market_cap: Optional[float]
    price_license: LicenseTag = LicenseTag.DEMO_ONLY
    as_of: Optional[pd.Timestamp] = None


@dataclass
class EstimateInputs:
    forward_eps: Optional[float] = None
    forward_label: str = "next fiscal year"
    growth: Optional[float] = None          # expected EPS growth, decimal
    growth_label: str = ""
    target_mean: Optional[float] = None
    target_low: Optional[float] = None
    target_high: Optional[float] = None


# name -> (label, unit, group, glossary key)
METRICS: dict[str, tuple[str, str, str, str]] = {
    "pe": ("P/E (TTM)", "x", "valuation", "pe"),
    "forward_pe": ("Forward P/E", "x", "valuation", "forward_pe"),
    "peg": ("PEG", "x", "valuation", "peg"),
    "ps": ("P/S (TTM)", "x", "valuation", "ps"),
    "pb": ("P/B", "x", "valuation", "pb"),
    "ev_ebitda": ("EV/EBITDA", "x", "valuation", "ev_ebitda"),
    "ev_revenue": ("EV/Revenue", "x", "valuation", "ev_revenue"),
    "p_fcf": ("P/FCF", "x", "valuation", "p_fcf"),
    "fcf_yield": ("FCF yield", "ratio", "valuation", "fcf_yield"),
    "earnings_yield": ("Earnings yield", "ratio", "valuation", "earnings_yield"),
    "enterprise_value": ("Enterprise value", "USD", "valuation", "enterprise_value"),
    "target_upside": ("Analyst target upside", "ratio", "valuation", "target_upside"),
    "roe": ("ROE", "ratio", "profitability", "roe"),
    "roa": ("ROA", "ratio", "profitability", "roa"),
    "roic": ("ROIC", "ratio", "profitability", "roic"),
    "gross_margin": ("Gross margin (TTM)", "ratio", "profitability", "margins"),
    "operating_margin": ("Operating margin (TTM)", "ratio", "profitability", "margins"),
    "ebitda_margin": ("EBITDA margin (TTM)", "ratio", "profitability", "margins"),
    "net_margin": ("Net margin (TTM)", "ratio", "profitability", "margins"),
    "asset_turnover": ("Asset turnover", "x", "profitability", "dupont"),
    "equity_multiplier": ("Equity multiplier", "x", "profitability", "dupont"),
    "effective_tax_rate": ("Effective tax rate (TTM)", "ratio", "profitability", "effective_tax_rate"),
    "revenue_yoy": ("Revenue growth YoY", "ratio", "growth", "growth"),
    "revenue_qoq": ("Revenue growth QoQ", "ratio", "growth", "growth"),
    "eps_yoy": ("EPS growth YoY", "ratio", "growth", "growth"),
    "revenue_cagr_3y": ("Revenue CAGR 3y", "ratio", "growth", "cagr"),
    "revenue_cagr_5y": ("Revenue CAGR 5y", "ratio", "growth", "cagr"),
    "net_income_cagr_3y": ("Net income CAGR 3y", "ratio", "growth", "cagr"),
    "net_income_cagr_5y": ("Net income CAGR 5y", "ratio", "growth", "cagr"),
    "eps_cagr_3y": ("EPS CAGR 3y", "ratio", "growth", "cagr"),
    "eps_cagr_5y": ("EPS CAGR 5y", "ratio", "growth", "cagr"),
    "fcf_cagr_3y": ("FCF CAGR 3y", "ratio", "growth", "cagr"),
    "fcf_cagr_5y": ("FCF CAGR 5y", "ratio", "growth", "cagr"),
    "net_debt": ("Net debt", "USD", "health", "net_debt"),
    "bvps": ("Book value per share", "USD/shares", "health", "bvps"),
    "current_ratio": ("Current ratio", "x", "health", "current_ratio"),
    "quick_ratio": ("Quick ratio", "x", "health", "quick_ratio"),
    "debt_to_equity": ("Debt to equity", "x", "health", "debt_to_equity"),
    "debt_to_ebitda": ("Debt to EBITDA", "x", "health", "debt_to_ebitda"),
    "interest_coverage": ("Interest coverage", "x", "health", "interest_coverage"),
    "fcf_ttm": ("Free cash flow (TTM)", "USD", "cashflow", "fcf"),
    "fcf_margin": ("FCF margin (TTM)", "ratio", "cashflow", "fcf"),
    "fcf_per_share": ("FCF per share (TTM)", "USD/shares", "cashflow", "fcf"),
    "cash_conversion": ("Cash conversion", "x", "cashflow", "cash_conversion"),
    "shareholder_returns": ("Shareholder returns (TTM)", "USD", "cashflow", "shareholder_returns"),
    "eps_ttm": ("EPS (TTM, diluted)", "USD/shares", "income", "eps_diluted"),
}

FINANCIAL_NA = {
    "ev_ebitda": "EBITDA is not meaningful for banks and insurers",
    "ebitda_margin": "EBITDA is not meaningful for banks and insurers",
    "debt_to_ebitda": "EBITDA is not meaningful for banks and insurers",
    "ev_revenue": "Enterprise value is not meaningful for banks (deposits act like debt)",
    "enterprise_value": "Enterprise value is not meaningful for banks (deposits act like debt)",
    "roic": "ROIC is not meaningful for banks and insurers (debt is their raw material); use ROE",
    "interest_coverage": "Not meaningful for banks (paying interest is their core business)",
    "current_ratio": "Banks and insurers don't split assets into current / non-current",
    "quick_ratio": "Banks and insurers don't split assets into current / non-current",
    "gross_margin": "Banks and insurers don't have a cost of revenue",
    "debt_to_equity": "Not meaningful for banks (deposits and borrowings are their core business)",
    "net_debt": "Not meaningful for banks (deposits and borrowings are their core business)",
    "p_fcf": "Free cash flow is not meaningful for banks (loans and deposits run through cash flow)",
    "fcf_yield": "Free cash flow is not meaningful for banks (loans and deposits run through cash flow)",
    "fcf_margin": "Free cash flow is not meaningful for banks (loans and deposits run through cash flow)",
    "fcf_per_share": "Free cash flow is not meaningful for banks (loans and deposits run through cash flow)",
    "cash_conversion": "Not meaningful for banks (loans and deposits run through operating cash flow)",
}


def _latest(q: pd.DataFrame, col: str, max_age_days: int = 200) -> tuple[Optional[float], Optional[pd.Timestamp]]:
    """Latest non-empty value, but only if it is recent (not from a stopped series)."""
    if q.empty or col not in q:
        return None, None
    s = q[col].dropna()
    if s.empty:
        return None, None
    if (q.index.max() - s.index.max()).days > max_age_days:
        return None, None
    return float(s.iloc[-1]), s.index[-1]


def compute_snapshot(fin: Financials, q: pd.DataFrame, market: MarketInputs, est: EstimateInputs,
                     splits: Optional[pd.Series] = None) -> dict[str, DataPoint]:
    """Current value of every metric as a DataPoint with source, license and N/A reason."""
    out: dict[str, DataPoint] = {}
    base_lic = LicenseTag.DEMO_ONLY if fin.source != Source.SEC.value else LicenseTag.CALCULATED_SAFE
    px_lic = combined_license(base_lic, market.price_license) if base_lic != LicenseTag.DEMO_ONLY else LicenseTag.DEMO_ONLY
    est_lic = LicenseTag.DEMO_ONLY

    def put(name, value, reason=None, lic=base_lic, as_of=None, note=None):
        if fin.is_financial and name in FINANCIAL_NA:
            out[name] = DataPoint.na(FINANCIAL_NA[name])
        elif value is None or (isinstance(value, float) and (math.isnan(value) or math.isinf(value))):
            out[name] = DataPoint.na(reason or "Not enough data")
        else:
            out[name] = DataPoint(value=float(value), source=Source.CALCULATED, license_tag=lic, derived=True,
                                  as_of=as_of.date() if hasattr(as_of, "date") else as_of, note=note)

    L = lambda col: _latest(q, col)  # noqa: E731
    rev, rev_d = L("revenue_ttm")
    ni, ni_d = L("net_income_ttm")
    eps, eps_d = L("eps_diluted_ttm")
    ebitda, _ = L("ebitda_ttm")
    fcf, fcf_d = L("fcf_ttm")
    equity, eq_d = L("equity")
    debt, _ = L("total_debt")
    cash_sti, _ = L("cash_sti")
    price, mcap = market.price, market.market_cap

    # ----- valuation (uses the price -> license follows the price source) -----
    ev = enterprise_value(mcap, debt, cash_sti)
    put("enterprise_value", ev, "Needs market cap", px_lic, note="Market cap + total debt - cash & short-term investments")
    if eps is not None:
        v, r = pe_ratio(price, eps)
        put("pe", v, r, px_lic, eps_d, note=f"Price / TTM diluted EPS (${eps:.2f})")
    else:  # e.g. BRK: no standard EPS -> market cap / net income gives the same ratio
        v, r = pe_ratio(mcap, ni)
        put("pe", v, r or "Needs EPS or net income", px_lic, ni_d, note="Market cap / TTM net income")
    v, r = pe_ratio(price, est.forward_eps)
    put("forward_pe", v, r if est.forward_eps is not None else "No analyst EPS estimate available", LicenseTag.DEMO_ONLY,
        note=f"Price / analysts' EPS estimate for {est.forward_label}" if est.forward_eps else None)
    pe_val = out["pe"].value
    if pe_val is not None and est.growth is not None and est.growth > 0:
        put("peg", pe_val / (est.growth * 100), lic=LicenseTag.DEMO_ONLY,
            note=f"P/E / expected EPS growth ({est.growth * 100:.1f}%, {est.growth_label})")
    else:
        put("peg", None, "Needs a positive P/E and positive expected growth")
    v, r = positive_div(mcap, rev, "N/A (no revenue)")
    put("ps", v, r, px_lic, rev_d, note="Market cap / TTM revenue")
    v, r = positive_div(mcap, equity, "N/A (negative shareholders' equity)")
    put("pb", v, r, px_lic, eq_d, note="Market cap / shareholders' equity")
    v, r = positive_div(ev, ebitda, "N/A (EBITDA is zero or negative)")
    put("ev_ebitda", v, r if ebitda is not None else "Needs EBITDA (operating income + D&A)", px_lic)
    v, r = positive_div(ev, rev, "N/A (no revenue)")
    put("ev_revenue", v, r, px_lic)
    v, r = positive_div(mcap, fcf, "N/A (negative free cash flow)")
    put("p_fcf", v, r if fcf is not None else "Needs free cash flow", px_lic, fcf_d)
    put("fcf_yield", safe_div(fcf, mcap), "Needs free cash flow and market cap", px_lic, fcf_d)
    put("earnings_yield", safe_div(eps, price) if eps is not None else safe_div(ni, mcap),
        "Needs earnings and price", px_lic, note="Earnings / price (the inverse of P/E)")
    if est.target_mean and price:
        put("target_upside", est.target_mean / price - 1, lic=est_lic,
            note=f"Mean analyst target ${est.target_mean:,.2f} vs price ${price:,.2f}")
    else:
        put("target_upside", None, "No analyst price targets available")
    put("eps_ttm", eps, "EPS not reported in a standard form", base_lic, eps_d)

    # ----- profitability -----
    for name, col in (("roe", "roe"), ("roa", "roa"), ("roic", "roic"), ("net_margin", "net_margin_ttm"),
                      ("gross_margin", "gross_margin_ttm"), ("operating_margin", "operating_margin_ttm"),
                      ("ebitda_margin", "ebitda_margin_ttm"), ("asset_turnover", "asset_turnover"),
                      ("equity_multiplier", "equity_multiplier"), ("effective_tax_rate", "eff_tax_ttm")):
        v, d = L(col)
        reason = {"roe": "N/A (needs positive average equity and 5 quarters of data)",
                  "roic": "N/A (needs operating income and positive invested capital)"}.get(name, "Not enough data")
        put(name, v, reason, base_lic, d)

    # ----- growth -----
    for name, field_name in (("revenue_yoy", "revenue_yoy"), ("revenue_qoq", "revenue_qoq"), ("eps_yoy", "eps_yoy")):
        s = fin.series(field_name, "Q")
        put(name, float(s.iloc[-1]) if len(s) else None, "Needs the same quarter a year earlier", base_lic,
            s.index[-1] if len(s) else None)
    for label, field_name in (("revenue", "revenue"), ("net_income", "net_income"), ("eps", "eps_diluted"), ("fcf", "fcf")):
        s = annual_series(fin, field_name, splits)
        for yrs in (3, 5):
            v, r = cagr_from_annual(s, yrs)
            put(f"{label}_cagr_{yrs}y", v, r, base_lic)

    # ----- health -----
    for name, col, reason in (("net_debt", "net_debt", "No debt or cash data"),
                              ("bvps", "bvps", "Needs equity and share count"),
                              ("current_ratio", "current_ratio", "Not reported"),
                              ("quick_ratio", "quick_ratio", "Not reported"),
                              ("debt_to_equity", "debt_to_equity", "N/A (no debt data or negative equity)"),
                              ("debt_to_ebitda", "debt_to_ebitda", "N/A (needs debt and positive EBITDA)"),
                              ("interest_coverage", "interest_coverage",
                               "N/A (no interest expense reported; often means little or no debt cost)")):
        v, d = L(col)
        put(name, v, reason, base_lic, d)

    # ----- cash flow -----
    for name, col, reason in (("fcf_ttm", "fcf_ttm", "Needs operating cash flow and capex"),
                              ("fcf_margin", "fcf_margin_ttm", "Needs FCF and revenue"),
                              ("fcf_per_share", "fcf_per_share", "Needs FCF and share count"),
                              ("cash_conversion", "cash_conversion", "N/A (needs positive net income)"),
                              ("shareholder_returns", "shareholder_returns_ttm", "No dividends or buybacks reported")):
        v, d = L(col)
        put(name, v, reason, base_lic, d)
    return out
