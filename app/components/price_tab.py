"""Tab 2: Price & Technicals - chart with overlays, indicators, support/resistance, signals, risk."""
from __future__ import annotations

from typing import Optional

import pandas as pd
import streamlit as st

from app.components import charts, ui
from core.glossary import tooltip
from core.models import DataPoint, Source
from core.price_service import PriceAnalysis
from core.risk import drawdown_series, rebased

RANGES = {"1M": pd.DateOffset(months=1), "3M": pd.DateOffset(months=3), "6M": pd.DateOffset(months=6),
          "1Y": pd.DateOffset(years=1), "3Y": pd.DateOffset(years=3), "5Y": pd.DateOffset(years=5)}
OVERLAYS = ["SMA 20", "SMA 50", "SMA 200", "Bollinger Bands", "Support / resistance", "Pivot points", "Earnings dates"]
DEFAULT_OVERLAYS = ["SMA 50", "SMA 200", "Support / resistance", "Earnings dates"]
SR_NOTE = "Support and resistance are areas where price reacted before. They are not guarantees."


def _dp(p: PriceAnalysis, value=1, note: Optional[str] = None) -> DataPoint:
    return DataPoint(value=value, source=Source.CALCULATED, license_tag=p.license_tag, derived=True,
                     note=note or f"Calculated from {p.source.value} daily prices")


def _help(*keys: str) -> str:
    return "\n\n---\n\n".join(tooltip(k, ui.lang()) for k in keys)


def _pct(v, signed=True) -> str:
    return "N/A" if v is None or pd.isna(v) else (f"{v * 100:+.1f}%" if signed else f"{v * 100:.1f}%")


def _chart_section(p: PriceAnalysis) -> None:
    c1, c2, c3 = st.columns([1.2, 3.2, 1.1])
    with c1:
        rng = st.segmented_control("Range", list(RANGES), default="1Y", required=True, key=f"px_range_{p.symbol}")
    with c2:
        overlays = st.segmented_control("Overlays", OVERLAYS, selection_mode="multi", default=DEFAULT_OVERLAYS,
                                        key=f"px_overlays_{p.symbol}")
    with c3:
        sr_win = st.segmented_control("S/R window", ["6M", "1Y", "2Y"], default="1Y", required=True,
                                      key=f"px_srwin_{p.symbol}",
                                      help="How much history is used to find support and resistance levels.")
    start = p.df.index[-1] - RANGES[rng]
    view = p.df[p.df.index >= start]
    sr = p.sr[sr_win.lower()]
    st.markdown("##### Price, volume, RSI and MACD", help=_help("price_chart", "sma", "rsi", "macd"))
    fig = charts.price_chart(view, set(overlays or []), sr=sr, pivots=p.pivots, earnings=p.earnings)
    st.plotly_chart(fig, key=f"{p.symbol}_pricechart", config={"displayModeBar": False, "scrollZoom": False})
    ui.badge(_dp(p))
    st.caption("Candles: green = closed higher than it opened, red = lower. Earnings markers: green = beat "
               "estimates, red = missed (hover for the surprise %). RSI lines at 30 and 70.")


def _levels(p: PriceAnalysis) -> None:
    sr_win = st.session_state.get(f"px_srwin_{p.symbol}", "1Y") or "1Y"
    sr = p.sr[sr_win.lower()]
    c1, c2 = st.columns([3, 2])
    with c1:
        st.markdown(f"##### Support and resistance ({sr_win} window)", help=tooltip("support_resistance", ui.lang()))
        st.info(SR_NOTE, icon="ℹ️")
        rows = []
        for l in sr.resistances[::-1] + sr.supports:
            rows.append({"level": f"{'R' if l.kind == 'resistance' else 'S'}{l.rank}", "type": l.kind.title(),
                         "price": ui.fmt_money(l.price), "distance": _pct(l.distance), "touches": l.touches,
                         "strength": round(l.strength, 1), "last touch": f"{l.last_touch:%Y-%m-%d}"})
        if rows:
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        ns, nr = sr.nearest_support, sr.nearest_resistance
        parts = []
        parts.append(f"Nearest support {ui.fmt_money(ns.price)} ({_pct(ns.distance)})" if ns
                     else "No support level below the price in this window (price is near its lows)")
        parts.append(f"nearest resistance {ui.fmt_money(nr.price)} ({_pct(nr.distance)})" if nr
                     else "no resistance level above the price in this window (price is near its highs)")
        st.caption(" · ".join(parts) + f". Levels within {ui.fmt_money(sr.tolerance)} are grouped together.")
        ui.badge(_dp(p))
    with c2:
        st.markdown("##### Weekly pivot points", help=tooltip("pivots", ui.lang()))
        pv = p.pivots
        if pv:
            price = p.snap.price
            st.dataframe(pd.DataFrame([{"level": k, "price": ui.fmt_money(pv[k]), "distance": _pct(pv[k] / price - 1)}
                                       for k in ("R2", "R1", "P", "S1", "S2")]), hide_index=True, width="stretch")
            st.caption(f"From the week ending {pv['week_ending']:%d %b %Y}.")
        else:
            st.caption("N/A (not enough price history)")


def _snapshot_cards(p: PriceAnalysis) -> None:
    s = p.snap
    st.markdown("##### Technical snapshot", help=f"As of {s.as_of:%d %b %Y}.")
    cols = st.columns(6)
    items = [
        ("RSI (14)", "rsi", f"{s.rsi14:.0f}" if s.rsi14 is not None else "N/A",
         None if s.rsi14 is None else ("overbought zone (>70)" if s.rsi14 > 70 else
                                       "oversold zone (<30)" if s.rsi14 < 30 else "neutral (30-70)")),
        ("MACD vs signal", "macd", f"{s.macd:+.2f}" if s.macd is not None else "N/A",
         None if s.macd is None or s.macd_signal is None else
         ("above signal line" if s.macd > s.macd_signal else "below signal line")),
        ("ATR (14)", "atr", ui.fmt_money(s.atr14), f"{s.atr_pct * 100:.1f}% of price" if s.atr_pct else None),
        ("Volume vs 20-day avg", "volume", f"{s.vol_vs_avg20:.2f}x" if s.vol_vs_avg20 else "N/A",
         f"avg {s.vol_avg20 / 1e6:,.1f}M / 50-day {s.vol_avg50 / 1e6:,.1f}M" if s.vol_avg20 and s.vol_avg50 else None),
        ("From 52-week high", "week52_range", _pct(s.from_high_52w), f"high {ui.fmt_money(s.high_52w)}"),
        ("From 52-week low", "week52_range", _pct(s.from_low_52w), f"low {ui.fmt_money(s.low_52w)}"),
    ]
    for col, (label, gkey, value, sub) in zip(cols, items):
        with col:
            st.metric(label, value, help=tooltip(gkey, ui.lang()))
            if sub:
                st.caption(sub)
    ui.badge(_dp(p))


def _signals(p: PriceAnalysis) -> None:
    st.markdown("##### Trend signals (facts, not advice)", help=tooltip("trend_signals", ui.lang()))
    icon = {"positive": "🟢", "negative": "🔴", "neutral": "⚪"}
    df = pd.DataFrame([{"": icon[s.tone], "signal": s.name, "what happened": s.fact,
                        "date": f"{s.date:%Y-%m-%d}" if s.date is not None else "—"} for s in p.signals])
    st.dataframe(df, hide_index=True, width="stretch")
    st.caption("🟢 / 🔴 only show the direction of each fact (up / down). They are not recommendations.")


def _risk(p: PriceAnalysis) -> None:
    r = p.risk
    st.markdown("##### Risk", help=_help("beta", "volatility", "max_drawdown", "sharpe"))
    cols = st.columns(6)
    cards = [("Beta (vs SPY, 2y weekly)", "beta", f"{r.beta:.2f}" if r.beta is not None else "N/A"),
             ("Volatility (1y)", "volatility", _pct(r.volatility_1y, signed=False)),
             ("Max drawdown (1y)", "max_drawdown", _pct(r.max_drawdown_1y)),
             ("Max drawdown (5y)", "max_drawdown", _pct(r.max_drawdown_5y)),
             ("From all-time high in data", "drawdown", _pct(r.current_drawdown)),
             ("Sharpe ratio (1y)", "sharpe", f"{r.sharpe_1y:.2f}" if r.sharpe_1y is not None else "N/A")]
    for col, (label, gkey, value) in zip(cols, cards):
        with col:
            st.metric(label, value, help=tooltip(gkey, ui.lang()))
    if r.risk_free is not None:
        st.caption(f"Risk-free rate for Sharpe: {r.risk_free * 100:.2f}% (average 13-week T-bill yield, last year).")
    ui.badge(_dp(p, note="Calculated from demo daily prices of the stock, SPY and ^IRX"))


def _performance(p: PriceAnalysis) -> None:
    rng = st.session_state.get(f"px_range_{p.symbol}", "1Y") or "1Y"
    st.markdown(f"##### Performance vs the market and sector ({rng}, starting at 100)",
                help=tooltip("relative_performance", ui.lang()))
    if p.benchmarks:
        start = p.total_return.index[-1] - RANGES[rng]
        rb = rebased({p.symbol: p.total_return, **p.benchmarks}, start)
        if not rb.empty:
            st.plotly_chart(charts.relative_performance(rb, p.symbol), key=f"{p.symbol}_relperf",
                            config={"displayModeBar": False})
    else:
        st.caption("N/A (benchmark prices unavailable)")

    st.markdown("##### Returns by period", help=tooltip("returns", ui.lang()))
    t = p.returns.T.copy()
    for bench in p.benchmarks:
        if bench in t.index:
            t.loc[f"{p.symbol} vs {bench} (pp)"] = (t.loc[p.symbol] - t.loc[bench])
    fmt = t.map(lambda v: "N/A" if v is None or pd.isna(v) else f"{v * 100:+.1f}%")
    fmt.index = [i.replace(" (pp)", " (difference)") for i in fmt.index]
    st.dataframe(fmt, width="stretch")
    sec = f" and sector ETF {p.sector_etf}" if p.sector_etf else ""
    st.caption(f"Total returns (dividends included) for {p.symbol}, SPY{sec}. 3Y and 5Y are cumulative, not per year.")
    st.download_button("Download CSV", t.to_csv().encode("utf-8"), file_name=f"{p.symbol}_returns.csv",
                       mime="text/csv", key=f"dl_ret_{p.symbol}")
    ui.badge(_dp(p))


def _drawdown_and_months(p: PriceAnalysis) -> None:
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("##### Drawdown: how far below its previous high (5 years)", help=tooltip("drawdown", ui.lang()))
        st.plotly_chart(charts.drawdown_chart(drawdown_series(p.total_return)), key=f"{p.symbol}_dd",
                        config={"displayModeBar": False})
    with c2:
        st.markdown("##### Monthly returns (seasonality)", help=tooltip("monthly_returns", ui.lang()))
        if not p.monthly.empty:
            st.plotly_chart(charts.monthly_heatmap(p.monthly, height=60 + 42 * len(p.monthly)),
                            key=f"{p.symbol}_monthly", config={"displayModeBar": False})
            st.download_button("Download CSV", p.monthly.to_csv().encode("utf-8"),
                               file_name=f"{p.symbol}_monthly_returns.csv", mime="text/csv",
                               key=f"dl_month_{p.symbol}")
        else:
            st.caption("N/A (not enough history)")
    ui.badge(_dp(p))


def render_price_tab(p: Optional[PriceAnalysis]) -> None:
    if p is None:
        st.info("Price history is not available for this ticker right now.")
        return
    if ui.hidden_by_safe_mode(_dp(p)):
        st.info(f"{ui.SAFE_MODE_TEXT}. Everything on this tab is calculated from daily prices, which come from a "
                "demo source until the Nanovest price feed is connected (PRICE_PROVIDER=nanovest).")
        return
    for w in p.warnings:
        st.warning(w, icon="⚠️")
    _chart_section(p)
    _levels(p)
    st.divider()
    _snapshot_cards(p)
    _signals(p)
    st.divider()
    _risk(p)
    _performance(p)
    _drawdown_and_months(p)
