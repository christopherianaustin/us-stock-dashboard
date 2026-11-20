"""Builds everything the Valuation and Profitability & Health tabs need for one ticker."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Optional

import pandas as pd

from core.financials import Financials
from core.logging_setup import get_logger
from core.models import DataPoint, HeaderData, LicenseTag, Source, combined_license
from core.providers import registry
from core.quality_scores import AltmanResult, PiotroskiResult, altman_z, piotroski
from core.ratios import (EstimateInputs, MarketInputs, compute_snapshot, graham_number, quarterly_metrics)
from core.valuation import (HistoryStats, dcf_default_growth, history_stats, peer_medians, peer_row,
                            valuation_history)

log = get_logger("analysis")


@dataclass
class Analysis:
    symbol: str
    snapshot: dict[str, DataPoint]
    quarterly: pd.DataFrame
    history: pd.DataFrame
    history_license: LicenseTag
    stats: dict[str, HistoryStats]
    peers: pd.DataFrame
    peer_medians: dict[str, Optional[float]]
    estimates: EstimateInputs
    graham: DataPoint
    dcf_inputs: dict[str, Any]
    piotroski: PiotroskiResult
    altman: AltmanResult
    yahoo_compare: pd.DataFrame
    price: Optional[float]
    warnings: list[str] = field(default_factory=list)


def _estimates(symbol: str, fin: Financials) -> EstimateInputs:
    yf = registry.yfinance()
    est = EstimateInputs()
    ee = yf.get_earnings_estimate(symbol)
    # Which fiscal year is "+1y"? If the latest reported quarter is Q4, the year in progress is next year.
    q = fin.tidy[fin.tidy["period_type"] == "Q"].sort_values("period_end")
    next_fy = None
    if not q.empty:
        last = q.iloc[-1]
        in_progress = int(last["fiscal_year"]) + (1 if last["fiscal_quarter"] == 4 else 0)
        next_fy = in_progress + 1
    if ee is not None and "+1y" in ee.index and pd.notna(ee.loc["+1y", "avg"]):
        est.forward_eps = float(ee.loc["+1y", "avg"])
        est.forward_label = f"next fiscal year (FY{next_fy})" if next_fy else "next fiscal year"
    ge = yf.get_growth_estimates(symbol)
    if ge is not None and "LTG" in ge.index and pd.notna(ge.loc["LTG", "stockTrend"]):
        est.growth, est.growth_label = float(ge.loc["LTG", "stockTrend"]), "long-term analyst estimate"
    elif ee is not None and "+1y" in ee.index and pd.notna(ee.loc["+1y", "growth"]):
        est.growth, est.growth_label = float(ee.loc["+1y", "growth"]), "analysts' next-year EPS growth"
    pt = yf.get_price_targets(symbol) or {}
    est.target_mean, est.target_low, est.target_high = pt.get("mean"), pt.get("low"), pt.get("high")
    return est


def _peers(symbols: list[str]) -> pd.DataFrame:
    if not symbols:
        return pd.DataFrame()
    yf = registry.yfinance()
    with ThreadPoolExecutor(max_workers=min(8, len(symbols))) as pool:
        infos = list(pool.map(lambda s: (s, yf.get_profile(s)), symbols))
    rows = [peer_row(s, info) for s, info in infos if info]
    return pd.DataFrame(rows)


YAHOO_COMPARE = [  # (our snapshot key, yfinance info key, scale)
    ("pe", "trailingPE", 1), ("ps", "priceToSalesTrailing12Months", 1), ("pb", "priceToBook", 1),
    ("ev_ebitda", "enterpriseToEbitda", 1), ("ev_revenue", "enterpriseToRevenue", 1),
    ("roe", "returnOnEquity", 1), ("roa", "returnOnAssets", 1), ("net_margin", "profitMargins", 1),
    ("debt_to_equity", "debtToEquity", 0.01), ("current_ratio", "currentRatio", 1), ("quick_ratio", "quickRatio", 1),
]


def _yahoo_compare(snapshot: dict[str, DataPoint], info: Optional[dict]) -> pd.DataFrame:
    rows = []
    for ours, key, scale in YAHOO_COMPARE:
        y = (info or {}).get(key)
        y = float(y) * scale if isinstance(y, (int, float)) else None
        o = snapshot.get(ours)
        ov = o.value if o is not None and o.available else None
        diff = (ov / y - 1) if (ov is not None and y) else None
        rows.append({"metric": ours, "ours": ov, "yahoo": y, "difference": diff})
    return pd.DataFrame(rows)


def load_analysis(symbol: str, header: HeaderData, fin: Optional[Financials]) -> Optional[Analysis]:
    if fin is None or not fin.available:
        return None
    yf = registry.yfinance()
    warnings: list[str] = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        f_splits = pool.submit(yf.get_splits, symbol)
        f_est = pool.submit(_estimates, symbol, fin)
        f_hist = pool.submit(registry.get_history, symbol, "5y")
        peer_syms = header.profile.peers.value if header.profile.peers.available else []
        f_peers = pool.submit(_peers, list(peer_syms)[:8])
        splits = f_splits.result()
        try:
            est = f_est.result()
        except Exception as exc:  # noqa: BLE001
            log.warning("estimates failed for %s: %s", symbol, exc)
            est, _ = EstimateInputs(), warnings.append("Analyst estimates could not be loaded.")
        hist_df, hist_provider = f_hist.result()
        try:
            peers = f_peers.result()
        except Exception as exc:  # noqa: BLE001
            log.warning("peers failed for %s: %s", symbol, exc)
            peers = pd.DataFrame()

    q = quarterly_metrics(fin, splits)
    price = header.price.value if header.price.available else None
    price_lic = header.price.license_tag or LicenseTag.DEMO_ONLY
    mcap = header.market_cap.value if header.market_cap.available else None
    market = MarketInputs(price=price, market_cap=mcap, price_license=price_lic)
    snap = compute_snapshot(fin, q, market, est, splits)

    # ----- valuation history (5 years, no look-ahead) -----
    history = pd.DataFrame()
    hist_lic = LicenseTag.DEMO_ONLY
    if hist_df is not None and not hist_df.empty:
        history = valuation_history(q, hist_df["Close"], fin.is_financial)
        base = LicenseTag.CALCULATED_SAFE if fin.source == Source.SEC.value else LicenseTag.DEMO_ONLY
        hist_lic = combined_license(base, hist_provider.license_tag)
    else:
        warnings.append("5-year price history is unavailable, so valuation history can't be shown.")
    stats = {}
    for k in ("pe", "ps", "ev_ebitda"):
        cur = snap[k].value if snap[k].available else None
        stats[k] = history_stats(history[k] if k in history else pd.Series(dtype=float), cur)

    # ----- fair value inputs -----
    eps = snap["eps_ttm"].value if snap["eps_ttm"].available else None
    bvps = snap["bvps"].value if snap["bvps"].available else None
    g_val, g_reason = graham_number(eps, bvps)
    graham = (DataPoint(value=g_val, source=Source.CALCULATED, license_tag=LicenseTag.CALCULATED_SAFE, derived=True,
                        note="Classic formula, estimate: sqrt(22.5 x EPS x book value per share)")
              if g_val is not None else DataPoint.na(g_reason))
    fcf_cagr = snap["fcf_cagr_3y"].value if snap["fcf_cagr_3y"].available else None
    growth, growth_src = dcf_default_growth(est.growth, fcf_cagr)
    last = q.iloc[-1] if not q.empty else pd.Series(dtype=float)
    shares = last.get("shares")
    if (shares is None or pd.isna(shares)) and mcap and price:
        shares = mcap / price
    dcf_inputs = {
        "fcf0": snap["fcf_ttm"].value if snap["fcf_ttm"].available else None,
        "growth": growth, "growth_source": growth_src, "discount": 0.10, "terminal": 0.025,
        "net_debt": snap["net_debt"].value if snap["net_debt"].available else 0.0,
        "shares": float(shares) if shares is not None and not pd.isna(shares) else None,
        "not_meaningful": "A free-cash-flow DCF is not meaningful for banks and insurers" if fin.is_financial else None,
    }

    return Analysis(
        symbol=symbol, snapshot=snap, quarterly=q, history=history, history_license=hist_lic, stats=stats,
        peers=peers, peer_medians=peer_medians(peers) if not peers.empty else {}, estimates=est, graham=graham,
        dcf_inputs=dcf_inputs, piotroski=piotroski(fin), altman=altman_z(q, mcap, fin.is_financial),
        yahoo_compare=_yahoo_compare(snap, yf.get_profile(symbol)), price=price, warnings=warnings,
    )
