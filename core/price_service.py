"""Loads prices + benchmarks and computes technicals and risk for the Price & Technicals tab."""
from __future__ import annotations

import functools
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd
import yaml

from config.settings import CONFIG_DIR
from core.logging_setup import get_logger
from core.models import LicenseTag, Source
from core.providers import registry
from core.risk import RiskMetrics, monthly_returns, returns_table, risk_metrics
from core.technicals import (SRResult, Signal, TechSnapshot, add_indicators, snapshot, support_resistance,
                             trend_signals, weekly_pivots)

log = get_logger("price_service")


@functools.lru_cache(maxsize=1)
def sector_etf_map() -> dict[str, str]:
    with open(CONFIG_DIR / "sector_etfs.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


@dataclass
class PriceAnalysis:
    symbol: str
    df: pd.DataFrame                    # 5y daily OHLCV + indicators (tz-naive index)
    total_return: pd.Series             # adjusted close (includes dividends) for returns / risk
    snap: TechSnapshot
    signals: list[Signal]
    sr: dict[str, SRResult]             # "6m" / "1y" / "2y"
    pivots: Optional[dict]
    returns: pd.DataFrame               # periods x [stock, SPY, sector ETF]
    risk: RiskMetrics
    benchmarks: dict[str, pd.Series]    # name -> adjusted close
    sector_etf: Optional[str]
    monthly: pd.DataFrame
    earnings: pd.DataFrame              # date, eps_estimate, eps_reported, surprise_pct, timing
    source: Source
    license_tag: LicenseTag
    warnings: list[str] = field(default_factory=list)


def _naive(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    idx = pd.DatetimeIndex(df.index)
    if idx.tz is not None:
        idx = idx.tz_localize(None)
    df.index = idx.normalize()
    return df[~df.index.duplicated(keep="last")].sort_index()


def _adj(df: Optional[pd.DataFrame]) -> Optional[pd.Series]:
    if df is None or df.empty:
        return None
    df = _naive(df)
    col = "Adj Close" if "Adj Close" in df and df["Adj Close"].notna().any() else "Close"
    return df[col].dropna()


def _earnings_table(raw: Optional[pd.DataFrame]) -> pd.DataFrame:
    cols = ["date", "datetime", "eps_estimate", "eps_reported", "surprise_pct", "timing"]
    if raw is None or raw.empty:
        return pd.DataFrame(columns=cols)
    rows = []
    for ts, r in raw.iterrows():
        ts = pd.Timestamp(ts)
        local = ts.tz_convert("America/New_York") if ts.tzinfo else ts
        hour = local.hour + local.minute / 60
        timing = "before open" if hour < 9.5 else ("after close" if hour >= 16 else "unknown")
        if hour == 0:
            timing = "unknown"
        rows.append({"date": pd.Timestamp(local.date()), "datetime": local,
                     "eps_estimate": r.get("EPS Estimate"), "eps_reported": r.get("Reported EPS"),
                     "surprise_pct": r.get("Surprise(%)"), "timing": timing})
    return pd.DataFrame(rows, columns=cols).sort_values("date").reset_index(drop=True)


def load_price_analysis(symbol: str, sector: Optional[str]) -> Optional[PriceAnalysis]:
    yf = registry.yfinance()
    etfs = sector_etf_map()
    etf = etfs.get(sector) if sector else None
    market, rf_symbol = etfs.get("_market", "SPY"), etfs.get("_risk_free", "^IRX")
    warnings: list[str] = []

    with ThreadPoolExecutor(max_workers=5) as pool:
        f_hist = pool.submit(registry.get_history, symbol, "5y")
        f_spy = pool.submit(yf.get_history_raw, market, "5y")
        f_etf = pool.submit(yf.get_history_raw, etf, "5y") if etf else None
        f_rf = pool.submit(yf.get_history_raw, rf_symbol, "1y")
        f_earn = pool.submit(yf.get_earnings_dates, symbol)
        hist, provider = f_hist.result()
        spy_raw, etf_raw, rf_raw = f_spy.result(), (f_etf.result() if f_etf else None), f_rf.result()
        try:
            earn_raw = f_earn.result()
        except Exception as exc:  # noqa: BLE001
            log.warning("earnings dates failed: %s", exc)
            earn_raw = None

    if hist is None or hist.empty or provider is None:
        return None
    df = add_indicators(_naive(hist)[["Open", "High", "Low", "Close", "Volume"]].dropna(subset=["Close"]))
    tr = _adj(hist)
    spy, etf_s = _adj(spy_raw), _adj(etf_raw)
    if spy is None:
        warnings.append(f"Benchmark ({market}) prices are unavailable; relative performance and beta are hidden.")
    if etf and etf_s is None:
        warnings.append(f"Sector ETF ({etf}) prices are unavailable.")
    rf = None
    if rf_raw is not None and not rf_raw.empty:
        rf = float(rf_raw["Close"].dropna().mean()) / 100   # ^IRX is quoted in percent
    else:
        warnings.append("Risk-free rate (^IRX) unavailable, so the Sharpe ratio is hidden.")

    benchmarks = {market: spy} if spy is not None else {}
    if etf_s is not None:
        benchmarks[etf] = etf_s
    series = {symbol: tr, **benchmarks}
    return PriceAnalysis(
        symbol=symbol, df=df, total_return=tr, snap=snapshot(df), signals=trend_signals(df),
        sr={w: support_resistance(df, w) for w in ("6m", "1y", "2y")}, pivots=weekly_pivots(df),
        returns=returns_table(series), risk=risk_metrics(tr, spy, rf), benchmarks=benchmarks,
        sector_etf=etf if etf_s is not None else None, monthly=monthly_returns(tr),
        earnings=_earnings_table(earn_raw), source=provider.source,
        license_tag=LicenseTag.DEMO_ONLY if provider.license_tag == LicenseTag.DEMO_ONLY else LicenseTag.CALCULATED_SAFE,
        warnings=warnings,
    )
