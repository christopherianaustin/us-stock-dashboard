"""Risk and performance (SPEC 6.9): returns, relative performance, beta, volatility,
drawdowns, Sharpe ratio, monthly returns. Pure functions on daily price Series."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

TRADING_DAYS = 252
PERIODS = {  # label -> calendar offset (None = special)
    "1D": None, "1W": pd.DateOffset(weeks=1), "1M": pd.DateOffset(months=1), "3M": pd.DateOffset(months=3),
    "6M": pd.DateOffset(months=6), "YTD": None, "1Y": pd.DateOffset(years=1), "3Y": pd.DateOffset(years=3),
    "5Y": pd.DateOffset(years=5),
}


def period_return(s: pd.Series, label: str) -> Optional[float]:
    """Return over a period: last price / price at (or just before) the start date - 1.
    None if the history doesn't reach back far enough."""
    s = s.dropna()
    if len(s) < 2:
        return None
    end = s.index[-1]
    if label == "1D":
        return float(s.iloc[-1] / s.iloc[-2] - 1)
    if label == "YTD":
        start = pd.Timestamp(year=end.year, month=1, day=1)
        prior = s[s.index < start]
        return float(s.iloc[-1] / prior.iloc[-1] - 1) if len(prior) else None
    start = end - PERIODS[label]
    if s.index[0] > start + pd.Timedelta(days=5):   # history too short
        return None
    base = s[s.index <= start]
    # history may start a few days after the exact start date (weekend/holiday) -> use the first price
    base_price = base.iloc[-1] if len(base) else s.iloc[0]
    return float(s.iloc[-1] / base_price - 1)


def returns_table(series: dict[str, pd.Series]) -> pd.DataFrame:
    """Rows = periods, columns = series names (stock, SPY, sector ETF)."""
    return pd.DataFrame({name: {p: period_return(s, p) for p in PERIODS}
                         for name, s in series.items()}).astype(float)


def beta(stock: pd.Series, market: pd.Series, years: int = 2) -> Optional[float]:
    """Beta from WEEKLY returns over `years`: cov(stock, market) / var(market)."""
    end = stock.index[-1]
    w = pd.concat([stock, market], axis=1, keys=["s", "m"]).dropna()
    w = w[w.index > end - pd.DateOffset(years=years)].resample("W-FRI").last().pct_change().dropna()
    if len(w) < 52 or w["m"].var() == 0:
        return None
    return float(w["s"].cov(w["m"]) / w["m"].var())


def volatility(s: pd.Series, years: int = 1) -> Optional[float]:
    """Annualized volatility = std of daily returns x sqrt(252)."""
    r = s[s.index > s.index[-1] - pd.DateOffset(years=years)].pct_change().dropna()
    return float(r.std() * np.sqrt(TRADING_DAYS)) if len(r) > 20 else None


def drawdown_series(s: pd.Series) -> pd.Series:
    """How far below its previous peak the price is on each day (0 = at a new high)."""
    return s / s.cummax() - 1


def max_drawdown(s: pd.Series, years: Optional[int] = None) -> Optional[float]:
    if years is not None:
        start = s.index[-1] - pd.DateOffset(years=years)
        if s.index[0] > start + pd.Timedelta(days=5):
            return None
        s = s[s.index > start]
    return float(drawdown_series(s).min()) if len(s) > 1 else None


def sharpe(s: pd.Series, risk_free_annual: float, years: int = 1) -> Optional[float]:
    """Sharpe = (1-year return - risk-free rate) / annualized volatility."""
    ret = period_return(s, "1Y") if years == 1 else None
    vol = volatility(s, years)
    if ret is None or not vol:
        return None
    return (ret - risk_free_annual) / vol


def monthly_returns(s: pd.Series) -> pd.DataFrame:
    """Years x months table of monthly returns (for a seasonality heatmap)."""
    m = s.resample("ME").last().pct_change().dropna()
    if m.empty:
        return pd.DataFrame()
    t = pd.DataFrame({"year": m.index.year, "month": m.index.month, "ret": m.values})
    out = t.pivot(index="year", columns="month", values="ret").reindex(columns=range(1, 13))
    out.columns = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    return out.sort_index(ascending=False)


def rebased(series: dict[str, pd.Series], start: pd.Timestamp) -> pd.DataFrame:
    """All series = 100 on the first common day on/after `start` (relative performance chart)."""
    df = pd.concat(series, axis=1).dropna()
    df = df[df.index >= start]
    if df.empty:
        return df
    return df / df.iloc[0] * 100


@dataclass
class RiskMetrics:
    beta: Optional[float]
    volatility_1y: Optional[float]
    max_drawdown_1y: Optional[float]
    max_drawdown_5y: Optional[float]
    current_drawdown: Optional[float]
    sharpe_1y: Optional[float]
    risk_free: Optional[float]


def risk_metrics(stock: pd.Series, market: Optional[pd.Series], risk_free_annual: Optional[float]) -> RiskMetrics:
    return RiskMetrics(
        beta=beta(stock, market) if market is not None and not market.empty else None,
        volatility_1y=volatility(stock),
        max_drawdown_1y=max_drawdown(stock, 1),
        max_drawdown_5y=max_drawdown(stock, 5) if len(stock) else None,
        current_drawdown=float(stock.iloc[-1] / stock.max() - 1) if len(stock) else None,
        sharpe_1y=sharpe(stock, risk_free_annual) if risk_free_annual is not None else None,
        risk_free=risk_free_annual,
    )
