"""Dividend analytics (SPEC 6.6). Pure functions on a dividend Series
(dividend per share indexed by ex-dividend date) and daily prices."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd

from core.ratios import cagr


def pays_dividend(divs: Optional[pd.Series], today: Optional[pd.Timestamp] = None,
                  max_gap_days: int = 450) -> tuple[bool, Optional[str]]:
    """(pays?, reason). A company counts as paying if its last dividend was within ~15 months."""
    today = today or pd.Timestamp.today().normalize()
    if divs is None or len(divs) == 0:
        return False, "This company does not pay a dividend."
    last = divs.index.max()
    if (today - last).days > max_gap_days:
        return False, f"This company does not pay a dividend at the moment (last dividend paid in {last:%B %Y})."
    return True, None


def ttm_dps(divs: pd.Series, asof: Optional[pd.Timestamp] = None) -> float:
    """Dividends per share with an ex-date in the 365 days up to `asof`."""
    asof = asof or divs.index.max()
    return float(divs[(divs.index > asof - pd.Timedelta(days=365)) & (divs.index <= asof)].sum())


def payments_per_year(divs: pd.Series) -> Optional[int]:
    """Typical frequency (1, 2, 4 or 12) from the last 2 years."""
    recent = divs[divs.index > divs.index.max() - pd.Timedelta(days=730)]
    n = round(len(recent) / 2)
    for f in (12, 4, 2, 1):
        if n >= f * 0.75:
            return f
    return None


def annual_dps(divs: pd.Series, include_current: bool = False) -> pd.Series:
    """Total dividend per share per calendar year (complete years only unless include_current)."""
    s = divs.groupby(divs.index.year).sum()
    if not include_current:
        s = s[s.index < pd.Timestamp.today().year]
    return s


def growth_streak(divs: pd.Series) -> int:
    """Consecutive years (counting back from the last complete year) in which the regular dividend was
    raised. Compares each year's highest REGULAR payment: payments above 1.5x the year's median are treated
    as special dividends and ignored (e.g. KO's double payment in 2001, MSFT's $3 special in 2004).
    A raise in the last payment of the year (MSFT 2010) still counts."""
    def regular_max(x: pd.Series) -> float:
        med = x.median()
        return float(x[x <= med * 1.5].max())

    peak = divs.groupby(divs.index.year).apply(regular_max)
    peak = peak[peak.index < pd.Timestamp.today().year]
    streak = 0
    years = list(peak.index)
    for i in range(len(years) - 1, 0, -1):
        if years[i] - years[i - 1] != 1:
            break
        if peak.iloc[i] > peak.iloc[i - 1] * 1.0005:   # ignore rounding noise
            streak += 1
        else:
            break
    return streak


def dividend_cagr(divs: pd.Series, years: int) -> Optional[float]:
    a = annual_dps(divs)
    if len(a) < years + 1:
        return None
    last = a.index.max()
    if last - years not in a.index:
        return None
    return cagr(a[last - years], a[last], years)


def yield_history(divs: pd.Series, close: pd.Series) -> pd.Series:
    """Daily TTM dividend yield = last year of payments / closing price.
    'Last year of payments' = the last N payments for an N-times-a-year payer. A fixed 365-day window would
    spike whenever payment dates shift by a day (5 or 3 quarterly payments in the window)."""
    close = close.dropna()
    if close.empty or divs is None or len(divs) == 0:
        return pd.Series(dtype=float)
    n = payments_per_year(divs) or 4
    d = divs.sort_index()
    ttm_at_payment = d.rolling(n, min_periods=n).sum().dropna()
    ttm = ttm_at_payment.reindex(ttm_at_payment.index.union(close.index)).ffill().reindex(close.index)
    # stop counting a dividend that hasn't been followed by another for ~15 months (dividend suspended)
    last_pay = pd.Series(d.index, index=d.index).reindex(d.index.union(close.index)).ffill().reindex(close.index)
    stale = (close.index - pd.DatetimeIndex(last_pay)).days > 450
    return (ttm / close).where((close > 0) & ~stale)


@dataclass
class DividendSummary:
    pays: bool
    reason: Optional[str]
    dps_ttm: Optional[float]
    yield_ttm: Optional[float]
    frequency: Optional[int]
    cagr_3y: Optional[float]
    cagr_5y: Optional[float]
    streak: int
    yield_5y_avg: Optional[float]
    last_ex_date: Optional[pd.Timestamp]
    last_amount: Optional[float]


def summarize(divs: Optional[pd.Series], close: Optional[pd.Series], price: Optional[float]) -> DividendSummary:
    pays, reason = pays_dividend(divs)
    if not pays:
        return DividendSummary(False, reason, None, None, None, None, None, 0, None,
                               divs.index.max() if divs is not None and len(divs) else None,
                               float(divs.iloc[-1]) if divs is not None and len(divs) else None)
    dps = ttm_dps(divs, pd.Timestamp.today().normalize())
    yh = yield_history(divs, close) if close is not None else pd.Series(dtype=float)
    y5 = yh[yh.index > yh.index.max() - pd.DateOffset(years=5)].mean() if len(yh) else None
    return DividendSummary(
        pays=True, reason=None, dps_ttm=dps, yield_ttm=(dps / price) if price else None,
        frequency=payments_per_year(divs), cagr_3y=dividend_cagr(divs, 3), cagr_5y=dividend_cagr(divs, 5),
        streak=growth_streak(divs), yield_5y_avg=float(y5) if y5 is not None and pd.notna(y5) else None,
        last_ex_date=divs.index.max(), last_amount=float(divs.iloc[-1]))
