"""Piotroski F-score and Altman Z-score (SPEC 6.7), from SEC annual data."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

from core.financials import Financials, wide


@dataclass
class Check:
    name: str
    passed: Optional[bool]     # None = could not be calculated
    explanation: str
    detail: str = ""


@dataclass
class PiotroskiResult:
    score: int
    tested: int
    checks: list[Check] = field(default_factory=list)
    fiscal_year: Optional[int] = None
    reason: Optional[str] = None


def _v(row: pd.Series, f: str) -> Optional[float]:
    v = row.get(f) if row is not None else None
    return None if v is None or pd.isna(v) else float(v)


def _div(a, b):
    return None if a is None or b is None or b == 0 else a / b


def piotroski(fin: Financials) -> PiotroskiResult:
    """9 pass/fail tests comparing the latest fiscal year with the year before."""
    a = wide(fin.tidy, "FY")
    if len(a) < 3:
        return PiotroskiResult(0, 0, reason="Needs at least 3 fiscal years of data")
    a = a.sort_index()
    cur, prev, prev2 = a.iloc[-1], a.iloc[-2], a.iloc[-3]
    fy = int(fin.tidy[(fin.tidy.period_type == "FY") & (fin.tidy.period_end == a.index[-1])]["fiscal_year"].iloc[0])

    def roa(row, begin_row):
        return _div(_v(row, "net_income"), _v(begin_row, "total_assets"))

    def lev(row, begin_row):
        ltd = _v(row, "long_term_debt")
        assets = [x for x in (_v(row, "total_assets"), _v(begin_row, "total_assets")) if x]
        if not assets:
            return None
        return (ltd or 0) / (sum(assets) / len(assets))

    def cr(row):
        return _div(_v(row, "current_assets"), _v(row, "current_liabilities"))

    def gm(row):
        gp = _v(row, "gross_profit")
        if gp is None and _v(row, "cost_of_revenue") is not None and _v(row, "revenue") is not None:
            gp = _v(row, "revenue") - _v(row, "cost_of_revenue")
        return _div(gp, _v(row, "revenue"))

    def turnover(row, begin_row):
        return _div(_v(row, "revenue"), _v(begin_row, "total_assets"))

    roa_c, roa_p = roa(cur, prev), roa(prev, prev2)
    cfo, ni = _v(cur, "operating_cash_flow"), _v(cur, "net_income")
    lev_c, lev_p = lev(cur, prev), lev(prev, prev2)
    cr_c, cr_p = cr(cur), cr(prev)
    sh_c, sh_p = _v(cur, "diluted_shares"), _v(prev, "diluted_shares")
    gm_c, gm_p = gm(cur), gm(prev)
    to_c, to_p = turnover(cur, prev), turnover(prev, prev2)

    def cmp(x, y, fn):
        return None if x is None or y is None else bool(fn(x, y))

    pct = lambda x: "N/A" if x is None else f"{x * 100:.1f}%"  # noqa: E731
    num = lambda x: "N/A" if x is None else f"{x:.2f}"  # noqa: E731
    checks = [
        Check("Profitable (positive ROA)", None if roa_c is None else roa_c > 0,
              "The company made a profit relative to its assets.", f"ROA {pct(roa_c)}"),
        Check("Positive operating cash flow", None if cfo is None else cfo > 0,
              "The business generated cash from its operations.", f"OCF {num(cfo / 1e9 if cfo else None)}B"),
        Check("ROA improving", cmp(roa_c, roa_p, lambda x, y: x > y),
              "Profitability on assets is better than last year.", f"{pct(roa_p)} → {pct(roa_c)}"),
        Check("Cash flow above profit", cmp(cfo, ni, lambda x, y: x > y),
              "Operating cash flow is higher than net income, a sign of good earnings quality.",
              f"OCF {num(cfo / 1e9 if cfo else None)}B vs NI {num(ni / 1e9 if ni else None)}B"),
        Check("Leverage falling", cmp(lev_c, lev_p, lambda x, y: x <= y),
              "Long-term debt relative to assets went down (or stayed at zero).",
              f"{pct(lev_p)} → {pct(lev_c)}"),
        Check("Current ratio rising", cmp(cr_c, cr_p, lambda x, y: x > y),
              "The ability to pay short-term bills improved.", f"{num(cr_p)} → {num(cr_c)}"),
        Check("No new shares issued", cmp(sh_c, sh_p, lambda x, y: x <= y),
              "The share count did not increase, so owners were not diluted.",
              f"{num(sh_p / 1e9 if sh_p else None)}B → {num(sh_c / 1e9 if sh_c else None)}B shares"),
        Check("Gross margin rising", cmp(gm_c, gm_p, lambda x, y: x > y),
              "The company kept more of each sale after production costs.", f"{pct(gm_p)} → {pct(gm_c)}"),
        Check("Asset turnover rising", cmp(to_c, to_p, lambda x, y: x > y),
              "The company generated more sales per dollar of assets.", f"{num(to_p)} → {num(to_c)}"),
    ]
    tested = sum(c.passed is not None for c in checks)
    score = sum(bool(c.passed) for c in checks)
    return PiotroskiResult(score=score, tested=tested, checks=checks, fiscal_year=fy)


@dataclass
class AltmanResult:
    z: Optional[float]
    zone: Optional[str]
    parts: dict = field(default_factory=dict)
    reason: Optional[str] = None


def altman_zone(z: float) -> str:
    if z > 2.99:
        return "Safe"
    if z >= 1.81:
        return "Grey"
    return "Distress"


def altman_z(q: pd.DataFrame, market_cap: Optional[float], is_financial: bool) -> AltmanResult:
    """Z = 1.2 A + 1.4 B + 3.3 C + 0.6 D + 1.0 E (original formula for non-financial companies):
       A = working capital / total assets       B = retained earnings / total assets
       C = EBIT (TTM operating income) / assets D = market value of equity / total liabilities
       E = revenue (TTM) / total assets"""
    if is_financial:
        return AltmanResult(None, None, reason="Not used for banks and insurers (the formula was built for "
                                               "industrial companies, and their balance sheets work differently)")
    if q.empty:
        return AltmanResult(None, None, reason="Not enough data")
    row = q.iloc[-1]
    need = {"total_assets": row.get("total_assets"), "current_assets": row.get("current_assets"),
            "current_liabilities": row.get("current_liabilities"), "retained_earnings": row.get("retained_earnings"),
            "operating_income_ttm": row.get("operating_income_ttm"), "total_liabilities": row.get("total_liabilities"),
            "revenue_ttm": row.get("revenue_ttm")}
    missing = [k for k, v in need.items() if v is None or pd.isna(v)]
    if missing or not market_cap:
        return AltmanResult(None, None, reason="Missing inputs: " + ", ".join(missing + ([] if market_cap else ["market cap"])))
    ta = need["total_assets"]
    parts = {"A": (need["current_assets"] - need["current_liabilities"]) / ta,
             "B": need["retained_earnings"] / ta,
             "C": need["operating_income_ttm"] / ta,
             "D": market_cap / need["total_liabilities"],
             "E": need["revenue_ttm"] / ta}
    z = 1.2 * parts["A"] + 1.4 * parts["B"] + 3.3 * parts["C"] + 0.6 * parts["D"] + 1.0 * parts["E"]
    return AltmanResult(z=z, zone=altman_zone(z), parts=parts)
