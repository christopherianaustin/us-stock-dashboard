"""Shared Plotly chart helpers.

Color system (validated reference palette, see dataviz guidance):
  * series colors in a FIXED order (never cycled): SERIES[0] = the stock's main series
  * GOOD / BAD only when color means positive/beat vs negative/miss
  * GRAY for benchmarks / reference lines
One y-axis per chart (no dual axes). Thin rounded bars, hairline grid, hover shows exact values.
"""
from __future__ import annotations

import math
from typing import Optional, Sequence

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
GOOD = "#0ca30c"
BAD = "#d03b3b"
GRAY = "#898781"
GRID = "rgba(137,135,129,0.22)"


# ---------- value scaling / formats ----------
def money_scale(values: Sequence[float]) -> tuple[float, str]:
    arr = np.array([v for v in values if v is not None and not pd.isna(v)], dtype=float)
    m = np.abs(arr).max() if arr.size else 0
    if m >= 1e9:
        return 1e9, "B"
    if m >= 1e6:
        return 1e6, "M"
    if m >= 1e3:
        return 1e3, "K"
    return 1.0, ""


def _layout(fig: go.Figure, height: int = 340, y_title: str = "", tickformat: Optional[str] = None,
            tickprefix: str = "", ticksuffix: str = "", barmode: str = "group", legend: bool = True) -> go.Figure:
    fig.update_layout(
        height=height, margin=dict(l=8, r=8, t=28, b=8), barmode=barmode, bargap=0.28, bargroupgap=0.08,
        barcornerradius=4, hovermode="x unified", showlegend=legend,
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="left", x=0, title=None),
        font=dict(family='system-ui, -apple-system, "Segoe UI", sans-serif'),
    )
    fig.update_xaxes(showgrid=False, type="category", tickangle=0, automargin=True)
    fig.update_yaxes(showgrid=True, gridcolor=GRID, gridwidth=1, zeroline=True, zerolinecolor=GRAY, zerolinewidth=1,
                     title=y_title or None, tickformat=tickformat, tickprefix=tickprefix, ticksuffix=ticksuffix,
                     automargin=True)
    return fig


def _hover(name: str, kind: str, suffix: str = "") -> str:
    if kind == "money":
        return f"{name}: $%{{y:,.2f}}{suffix}<extra></extra>"
    if kind == "pct":
        return f"{name}: %{{y:.1%}}<extra></extra>"
    if kind == "x":
        return f"{name}: %{{y:.2f}}x<extra></extra>"
    if kind == "eps":
        return f"{name}: $%{{y:.2f}}<extra></extra>"
    return f"{name}: %{{y:,.2f}}<extra></extra>"


def _axis_kwargs(kind: str, suffix: str) -> dict:
    if kind == "money":
        return {"tickprefix": "$", "ticksuffix": suffix}
    if kind == "pct":
        return {"tickformat": ".0%"}
    if kind == "x":
        return {"ticksuffix": "x"}
    if kind == "eps":
        return {"tickprefix": "$"}
    return {}


def _end_labels(fig: go.Figure, x: list[str], series: list[tuple[str, list]], kind: str) -> None:
    """Direct-label the last point of each line (<= 4 series), in text ink, not series color."""
    if len(series) > 4:
        return
    for name, vals in series:
        idx = [i for i, v in enumerate(vals) if v is not None and not pd.isna(v)]
        if not idx:
            continue
        i = idx[-1]
        fig.add_annotation(x=x[i], y=vals[i], text=name, showarrow=False, xanchor="left", xshift=6,
                           font=dict(size=11, color=GRAY))


# ---------- chart builders ----------
def bars(x: list[str], series: list[tuple[str, list]], kind: str = "money", barmode: str = "group",
         colors: Optional[list[str]] = None, height: int = 340) -> go.Figure:
    allv = [v for _, vals in series for v in vals]
    div, suf = money_scale(allv) if kind == "money" else (1.0, "")
    fig = go.Figure()
    for i, (name, vals) in enumerate(series):
        y = [None if v is None or pd.isna(v) else v / div for v in vals]
        fig.add_bar(x=x, y=y, name=name, marker_color=(colors or SERIES)[i],
                    hovertemplate=_hover(name, kind, suf))
    return _layout(fig, height=height, barmode=barmode, legend=len(series) > 1, **_axis_kwargs(kind, suf))


def lines(x: list[str], series: list[tuple[str, list]], kind: str = "pct", colors: Optional[list[str]] = None,
          height: int = 320) -> go.Figure:
    allv = [v for _, vals in series for v in vals]
    div, suf = money_scale(allv) if kind == "money" else (1.0, "")
    fig = go.Figure()
    scaled = []
    for i, (name, vals) in enumerate(series):
        y = [None if v is None or pd.isna(v) else v / div for v in vals]
        scaled.append((name, y))
        fig.add_scatter(x=x, y=y, name=name, mode="lines+markers", connectgaps=False,
                        line=dict(color=(colors or SERIES)[i], width=2), marker=dict(size=8),
                        hovertemplate=_hover(name, kind, suf))
    _end_labels(fig, x, scaled, kind)
    fig.update_layout(margin=dict(r=90))
    return _layout(fig, height=height, legend=len(series) > 1, **_axis_kwargs(kind, suf))


def signed_bars(x: list[str], values: list, name: str, kind: str = "pct", height: int = 280) -> go.Figure:
    """Bars colored by sign: green for positive, red for negative."""
    y = [None if v is None or pd.isna(v) else v for v in values]
    colors = [GOOD if (v is not None and v >= 0) else BAD for v in y]
    fig = go.Figure(go.Bar(x=x, y=y, name=name, marker_color=colors, hovertemplate=_hover(name, kind)))
    return _layout(fig, height=height, legend=False, **_axis_kwargs(kind, ""))


def bars_over_line(x: list[str], bar_name: str, bar_vals: list, line_name: str, line_vals: list,
                   line_kind: str = "pct", height: int = 420) -> go.Figure:
    """Two stacked panels sharing the x-axis (instead of a dual-axis chart)."""
    div, suf = money_scale(bar_vals)
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.64, 0.36], vertical_spacing=0.08)
    fig.add_bar(x=x, y=[None if v is None or pd.isna(v) else v / div for v in bar_vals], name=bar_name,
                marker_color=SERIES[0], hovertemplate=_hover(bar_name, "money", suf), row=1, col=1)
    fig.add_scatter(x=x, y=[None if v is None or pd.isna(v) else v for v in line_vals], name=line_name,
                    mode="lines+markers", line=dict(color=SERIES[1], width=2), marker=dict(size=8),
                    hovertemplate=_hover(line_name, line_kind), row=2, col=1)
    _layout(fig, height=height, legend=True)
    fig.update_yaxes(tickprefix="$", ticksuffix=suf, row=1, col=1)
    fig.update_yaxes(**_axis_kwargs(line_kind, ""), row=2, col=1)
    return fig


def assets_vs_liabilities_equity(x: list[str], assets: list, liabilities: list, equity: list,
                                 height: int = 340) -> go.Figure:
    """Assets bar next to a stacked liabilities + equity bar (they should be equal)."""
    div, suf = money_scale(assets + liabilities + equity)
    sc = lambda vals: [None if v is None or pd.isna(v) else v / div for v in vals]  # noqa: E731
    fig = go.Figure()
    fig.add_bar(x=x, y=sc(assets), name="Total assets", marker_color=SERIES[0], offsetgroup="a",
                hovertemplate=_hover("Total assets", "money", suf))
    fig.add_bar(x=x, y=sc(liabilities), name="Liabilities", marker_color=SERIES[1], offsetgroup="b",
                hovertemplate=_hover("Liabilities", "money", suf))
    fig.add_bar(x=x, y=sc(equity), name="Equity", marker_color=SERIES[2], offsetgroup="b",
                base=[v or 0 for v in sc(liabilities)], hovertemplate=_hover("Equity", "money", suf))
    return _layout(fig, height=height, barmode="group", tickprefix="$", ticksuffix=suf)


STATUS_GOOD, STATUS_WARN, STATUS_CRIT = "#0ca30c", "#fab219", "#d03b3b"


def history_band(dates: pd.Index, values: pd.Series, name: str, median: Optional[float], std: Optional[float],
                 height: int = 340, band: bool = True) -> go.Figure:
    """Valuation multiple over time with its median and (optionally) a +/-1 standard deviation band."""
    fig = go.Figure()
    if band and median is not None and std:
        fig.add_scatter(x=list(dates) + list(dates[::-1]),
                        y=[median + std] * len(dates) + [median - std] * len(dates),
                        fill="toself", fillcolor="rgba(137,135,129,0.14)", line=dict(width=0),
                        hoverinfo="skip", name="±1 std. deviation")
    fig.add_scatter(x=dates, y=values, name=name, mode="lines", line=dict(color=SERIES[0], width=2),
                    hovertemplate=f"%{{x|%d %b %Y}}<br>{name}: %{{y:.1f}}x<extra></extra>")
    if median is not None:
        fig.add_hline(y=median, line=dict(color=GRAY, width=1.5),
                      annotation_text=f"5y median {median:.1f}x", annotation_position="top left",
                      annotation_font=dict(color=GRAY, size=11))
    _layout(fig, height=height, legend=band, ticksuffix="x")
    fig.update_xaxes(type="date")
    fig.update_layout(hovermode="x")
    return fig


def percentile_bars(items: list[tuple[str, float]], height: int = 200) -> go.Figure:
    """Horizontal bars 0-100: where today's multiple sits within its own 5-year history."""
    names = [n for n, _ in items]
    vals = [p * 100 for _, p in items]
    fig = go.Figure(go.Bar(y=names, x=vals, orientation="h", marker_color=SERIES[0],
                           text=[f"{v:.0f}%" for v in vals], textposition="outside", cliponaxis=False,
                           hovertemplate="%{y}: more expensive than %{x:.0f}% of the last 5 years<extra></extra>"))
    fig.add_vline(x=50, line=dict(color=GRAY, width=1),
                  annotation_text="typical", annotation_position="top", annotation_font=dict(color=GRAY, size=11))
    _layout(fig, height=height, legend=False)
    fig.update_xaxes(type="linear", range=[0, 110], showgrid=True, gridcolor=GRID, ticksuffix="%",
                     title="cheaper ← vs own history → more expensive")
    fig.update_yaxes(type="category", showgrid=False, autorange="reversed", zeroline=False, ticksuffix="")
    fig.update_layout(hovermode="closest")
    return fig


def peer_bars(tickers: list[str], values: list, highlight: str, median: Optional[float], kind: str,
              height: int = 320) -> go.Figure:
    """The stock in blue, peers in gray, peer median as a reference line."""
    colors = [SERIES[0] if t == highlight else "rgba(137,135,129,0.55)" for t in tickers]
    fig = go.Figure(go.Bar(x=tickers, y=values, marker_color=colors, hovertemplate=_hover("%{x}", kind)))
    if median is not None:
        label = f"{median * 100:.1f}%" if kind == "pct" else f"{median:.1f}x"
        fig.add_hline(y=median, line=dict(color=GRAY, width=1.5), annotation_text=f"peer median {label}",
                      annotation_position="top left", annotation_font=dict(color=GRAY, size=11))
    return _layout(fig, height=height, legend=False, **_axis_kwargs(kind, ""))


def fair_value_chart(price: Optional[float], rows: list[tuple[str, Optional[float], Optional[float], Optional[float]]],
                     height: int = 280) -> go.Figure:
    """Horizontal ranges (low - high) with a central dot, and a vertical line at today's price.
    rows: (label, low, mid, high)"""
    fig = go.Figure()
    labels = [r[0] for r in rows]
    for label, lo, mid, hi in rows:
        if lo is not None and hi is not None:
            fig.add_scatter(x=[lo, hi], y=[label, label], mode="lines", line=dict(color=SERIES[0], width=6),
                            hovertemplate=f"{label}: ${lo:,.2f} – ${hi:,.2f}<extra></extra>", showlegend=False)
        if mid is not None:
            fig.add_scatter(x=[mid], y=[label], mode="markers",
                            marker=dict(color=SERIES[0], size=12, line=dict(color="white", width=2)),
                            hovertemplate=f"{label}: $%{{x:,.2f}}<extra></extra>", showlegend=False)
    if price:
        fig.add_vline(x=price, line=dict(color=GRAY, width=2),
                      annotation_text=f"Price ${price:,.2f}", annotation_position="top",
                      annotation_font=dict(color=GRAY, size=11))
    _layout(fig, height=height, legend=False)
    pts = [v for r in rows for v in r[1:] if v is not None] + ([price] if price else [])
    pad = (max(pts) - min(pts)) * 0.08 if pts else 0
    fig.update_xaxes(type="linear", showgrid=True, gridcolor=GRID, tickprefix="$",
                     range=[min(pts) - pad, max(pts) + pad] if pts else None)
    fig.update_yaxes(type="category", categoryorder="array", categoryarray=labels[::-1], showgrid=False,
                     zeroline=False, tickprefix="")
    fig.update_layout(hovermode="closest")
    return fig


def zone_gauge(value: float, zones: list[tuple[float, float, str]], axis_max: float, title: str,
               height: int = 240) -> go.Figure:
    """Gauge with colored zones (status colors), e.g. Altman Z distress / grey / safe."""
    axis_min = min(0.0, math.floor(value))  # negative scores (deep distress) extend the scale
    zones = [(axis_min if i == 0 else lo, hi, c) for i, (lo, hi, c) in enumerate(zones)]
    shown = min(value, axis_max)
    fig = go.Figure(go.Indicator(
        mode="gauge+number", value=value, number=dict(valueformat=".2f"),
        gauge=dict(axis=dict(range=[axis_min, axis_max]), bar=dict(color=SERIES[0], thickness=0.22),
                   steps=[dict(range=[lo, hi], color=c) for lo, hi, c in zones],
                   threshold=dict(line=dict(color=SERIES[0], width=4), value=shown)),
        title=dict(text=title, font=dict(size=13))))
    fig.update_layout(height=height, margin=dict(l=20, r=20, t=40, b=10))
    return fig


def radar(labels: list[str], scores: list[float], height: int = 380) -> go.Figure:
    """Pillar scores 0-100 on a radar (one series, so one color)."""
    r = list(scores) + [scores[0]]
    th = list(labels) + [labels[0]]
    fig = go.Figure(go.Scatterpolar(r=r, theta=th, fill="toself", fillcolor="rgba(42,120,214,0.18)",
                                    line=dict(color=SERIES[0], width=2), marker=dict(size=8),
                                    hovertemplate="%{theta}: %{r:.0f}/100<extra></extra>"))
    fig.update_layout(height=height, margin=dict(l=40, r=40, t=20, b=20), showlegend=False,
                      polar=dict(radialaxis=dict(range=[0, 100], tickvals=[40, 70, 100], gridcolor=GRID,
                                                 angle=90, tickfont=dict(size=10)),
                                 angularaxis=dict(gridcolor=GRID)),
                      font=dict(family='system-ui, -apple-system, "Segoe UI", sans-serif'))
    return fig


def mini_price(close: pd.Series, support: Optional[float], resistance: Optional[float],
               height: int = 260) -> go.Figure:
    fig = go.Figure(go.Scatter(x=close.index, y=close, mode="lines", line=dict(color=SERIES[0], width=2),
                               name="Price", hovertemplate="%{x|%d %b %Y}: $%{y:,.2f}<extra></extra>"))
    for lvl, color, name in ((support, GOOD, "Support"), (resistance, BAD, "Resistance")):
        if lvl:
            fig.add_hline(y=lvl, line=dict(color=color, width=1.5), annotation_text=f"{name} ${lvl:,.2f}",
                          annotation_position="bottom left" if name == "Support" else "top left",
                          annotation_font=dict(color=color, size=11))
    _layout(fig, height=height, legend=False, tickprefix="$")
    fig.update_xaxes(type="date")
    fig.update_layout(hovermode="x")
    return fig


def consensus_gauge(score: float, height: int = 220) -> go.Figure:
    """Analysts' average rating 1 (strong buy) .. 5 (strong sell) - third-party opinion, neutral styling."""
    fig = go.Figure(go.Indicator(
        mode="gauge+number", value=score, number=dict(valueformat=".2f"),
        gauge=dict(axis=dict(range=[1, 5], tickvals=[1, 2, 3, 4, 5],
                             ticktext=["Strong buy", "Buy", "Hold", "Sell", "Strong sell"]),
                   bar=dict(color=SERIES[0], thickness=0.25),
                   steps=[dict(range=[1, 5], color="rgba(137,135,129,0.15)")])))
    fig.update_layout(height=height, margin=dict(l=30, r=30, t=20, b=10))
    return fig


def donut(labels: list[str], values: list[float], height: int = 300) -> go.Figure:
    """Part-to-whole with <= 6 segments, fixed categorical order, a 2px surface gap, values labeled."""
    fig = go.Figure(go.Pie(labels=labels, values=values, hole=0.55, sort=False, direction="clockwise",
                           marker=dict(colors=SERIES[:len(labels)], line=dict(color="rgba(0,0,0,0)", width=2)),
                           texttemplate="%{label}<br>%{percent:.1%}", textposition="outside",
                           hovertemplate="%{label}: %{percent:.1%}<extra></extra>"))
    fig.update_layout(height=height, margin=dict(l=10, r=10, t=10, b=10), showlegend=False,
                      font=dict(family='system-ui, -apple-system, "Segoe UI", sans-serif'))
    return fig


# Ordered categories (analysts' ratings): green shades -> gray -> red shades
RATING_COLORS = ["#006300", "#5cb85c", "#b9b7ae", "#ec835a", "#d03b3b"]


def stacked_ratings(months: list[str], series: list[tuple[str, list]], height: int = 320) -> go.Figure:
    fig = go.Figure()
    for (name, vals), color in zip(series, RATING_COLORS):
        fig.add_bar(x=months, y=vals, name=name, marker_color=color, hovertemplate=f"{name}: %{{y}} analysts<extra></extra>")
    return _layout(fig, height=height, barmode="stack")


def line_with_reference(dates, values, name: str, ref: Optional[float], ref_label: str, kind: str = "pct",
                        height: int = 300) -> go.Figure:
    fmt = ".2%" if kind == "pct" else ",.2f"
    fig = go.Figure(go.Scatter(x=dates, y=values, name=name, mode="lines", line=dict(color=SERIES[0], width=2),
                               hovertemplate=f"%{{x|%d %b %Y}}<br>{name}: %{{y:{fmt}}}<extra></extra>"))
    if ref is not None:
        txt = f"{ref * 100:.2f}%" if kind == "pct" else f"{ref:,.2f}"
        fig.add_hline(y=ref, line=dict(color=GRAY, width=1.5), annotation_text=f"{ref_label} {txt}",
                      annotation_position="top left", annotation_font=dict(color=GRAY, size=11))
    _layout(fig, height=height, legend=False, tickformat=".1%" if kind == "pct" else None)
    fig.update_xaxes(type="date")
    fig.update_layout(hovermode="x")
    return fig


RESULT_COLORS = {"beat": GOOD, "miss": BAD, "inline": GRAY}


def eps_vs_estimate(x: list[str], estimate: list, actual: list, results: list, surprise: list,
                    height: int = 360) -> go.Figure:
    """Estimate bars in gray; actual bars green (beat) / red (miss) / gray (inline); surprise % above."""
    clean = lambda vals: [None if v is None or pd.isna(v) else float(v) for v in vals]  # noqa: E731
    fig = go.Figure()
    fig.add_bar(x=x, y=clean(estimate), name="Expected (analyst estimate)", marker_color="rgba(137,135,129,0.45)",
                hovertemplate="Expected EPS: $%{y:.3f}<extra></extra>")
    colors = [RESULT_COLORS.get(r, GRAY) for r in results]
    labels = ["" if s is None or pd.isna(s) else f"{s:+.1f}%" for s in surprise]
    fig.add_bar(x=x, y=clean(actual), name="Actual (reported EPS)", marker_color=colors, text=labels,
                textposition="outside", cliponaxis=False, textfont=dict(size=11),
                customdata=[r or "n/a" for r in results],
                hovertemplate="Actual EPS: $%{y:.2f} (%{customdata}, surprise %{text})<extra></extra>")
    return _layout(fig, height=height, tickprefix="$")


def revenue_vs_estimate(x: list[str], actual: list, estimate: list, height: int = 320) -> go.Figure:
    """Actual revenue bars with analyst-estimate markers where an estimate exists."""
    div, suf = money_scale(list(actual) + list(estimate))
    sc = lambda vals: [None if v is None or pd.isna(v) else float(v) / div for v in vals]  # noqa: E731
    fig = go.Figure()
    fig.add_bar(x=x, y=sc(actual), name="Actual revenue (SEC)", marker_color=SERIES[0],
                hovertemplate=_hover("Actual revenue", "money", suf))
    if any(v is not None and not pd.isna(v) for v in estimate):
        fig.add_scatter(x=x, y=sc(estimate), name="Expected revenue", mode="markers",
                        marker=dict(symbol="line-ew-open", size=26, color=GRAY, line=dict(width=3)),
                        hovertemplate=_hover("Expected revenue", "money", suf))
    return _layout(fig, height=height, tickprefix="$", ticksuffix=suf)


SMA_COLORS = {20: SERIES[3], 50: SERIES[1], 200: SERIES[6]}
SUPPORT_COLOR, RESIST_COLOR = GOOD, BAD


def price_chart(df: pd.DataFrame, overlays: set[str], sr=None, pivots: Optional[dict] = None,
                earnings: Optional[pd.DataFrame] = None, height: int = 820) -> go.Figure:
    """Candlesticks + volume + RSI + MACD as 4 stacked panels sharing one time axis."""
    fig = make_subplots(rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.025,
                        row_heights=[0.56, 0.12, 0.16, 0.16])
    x = df.index
    fig.add_trace(go.Candlestick(x=x, open=df["Open"], high=df["High"], low=df["Low"], close=df["Close"],
                                 name="Price", increasing=dict(line=dict(color=GOOD, width=1), fillcolor=GOOD),
                                 decreasing=dict(line=dict(color=BAD, width=1), fillcolor=BAD),
                                 showlegend=False), row=1, col=1)
    for n in (20, 50, 200):
        if f"SMA {n}" in overlays:
            fig.add_scatter(x=x, y=df[f"sma{n}"], name=f"SMA {n}", mode="lines",
                            line=dict(color=SMA_COLORS[n], width=1.6),
                            hovertemplate=f"SMA {n}: $%{{y:,.2f}}<extra></extra>", row=1, col=1)
    if "Bollinger Bands" in overlays:
        fig.add_scatter(x=x, y=df["bb_upper"], name="Bollinger upper", mode="lines",
                        line=dict(color=GRAY, width=1), hovertemplate="BB upper: $%{y:,.2f}<extra></extra>",
                        row=1, col=1)
        fig.add_scatter(x=x, y=df["bb_lower"], name="Bollinger lower", mode="lines", fill="tonexty",
                        fillcolor="rgba(137,135,129,0.10)", line=dict(color=GRAY, width=1),
                        hovertemplate="BB lower: $%{y:,.2f}<extra></extra>", row=1, col=1)
    x0, x1 = x[0], x[-1]
    if sr is not None and "Support / resistance" in overlays:
        for lvl in sr.supports + sr.resistances:
            color = SUPPORT_COLOR if lvl.kind == "support" else RESIST_COLOR
            tag = f"{'S' if lvl.kind == 'support' else 'R'}{lvl.rank} ${lvl.price:,.2f} · str. {lvl.strength:.1f}"
            fig.add_shape(type="line", x0=x0, x1=x1, y0=lvl.price, y1=lvl.price,
                          line=dict(color=color, width=1.5), opacity=0.8, row=1, col=1)
            # Label in the right margin (outside the plot) so candles never hide it
            fig.add_annotation(xref="paper", yref="y", x=1.0, y=lvl.price, text=tag, showarrow=False,
                               xanchor="left", yanchor="middle", xshift=4, font=dict(size=10, color=color))
    if pivots and "Pivot points" in overlays:
        for k in ("S2", "S1", "P", "R1", "R2"):
            fig.add_shape(type="line", x0=x0, x1=x1, y0=pivots[k], y1=pivots[k],
                          line=dict(color=GRAY, width=1), opacity=0.7, row=1, col=1)
            fig.add_annotation(x=x0, y=pivots[k], text=f"Pivot {k} ${pivots[k]:,.2f}", showarrow=False, xanchor="left",
                               yanchor="bottom", font=dict(size=10, color=GRAY), row=1, col=1)
    if earnings is not None and not earnings.empty and "Earnings dates" in overlays:
        e = earnings[(earnings["date"] >= x0) & (earnings["date"] <= x1)]
        if not e.empty:
            ys, txt, colors = [], [], []
            for _, r in e.iterrows():
                near = df.loc[df.index >= r["date"]].head(1)
                ys.append(float((near if len(near) else df.tail(1))["High"].iloc[0]) * 1.04)
                s = r["surprise_pct"]
                if pd.isna(s):
                    txt.append(f"Earnings {r['date']:%d %b %Y} ({r['timing']})<br>no surprise data")
                    colors.append(GRAY)
                else:
                    txt.append(f"Earnings {r['date']:%d %b %Y} ({r['timing']})<br>EPS surprise {s:+.1f}%")
                    colors.append(GOOD if s > 1 else (BAD if s < -1 else GRAY))
            fig.add_scatter(x=list(e["date"]), y=ys, mode="markers", name="Earnings",
                            marker=dict(symbol="diamond", size=11, color=colors, line=dict(color="white", width=1.5)),
                            hovertext=txt, hoverinfo="text", row=1, col=1)
    vol_colors = [GOOD if c >= o else BAD for o, c in zip(df["Open"], df["Close"])]
    fig.add_bar(x=x, y=df["Volume"], name="Volume", marker_color=vol_colors, opacity=0.55, showlegend=False,
                hovertemplate="Volume: %{y:,.0f}<extra></extra>", row=2, col=1)
    fig.add_scatter(x=x, y=df["vol_avg50"], name="50-day avg volume", mode="lines", line=dict(color=GRAY, width=1.2),
                    hovertemplate="50-day avg volume: %{y:,.0f}<extra></extra>", showlegend=False, row=2, col=1)
    fig.add_scatter(x=x, y=df["rsi14"], name="RSI 14", mode="lines", line=dict(color=SERIES[0], width=1.6),
                    hovertemplate="RSI: %{y:.1f}<extra></extra>", showlegend=False, row=3, col=1)
    for lvl in (30, 70):
        fig.add_hline(y=lvl, line=dict(color=GRAY, width=1), row=3, col=1)
    hist_colors = [GOOD if v >= 0 else BAD for v in df["hist"].fillna(0)]
    fig.add_bar(x=x, y=df["hist"], name="MACD histogram", marker_color=hist_colors, opacity=0.6, showlegend=False,
                hovertemplate="Histogram: %{y:.2f}<extra></extra>", row=4, col=1)
    fig.add_scatter(x=x, y=df["macd"], name="MACD", mode="lines", line=dict(color=SERIES[0], width=1.5),
                    hovertemplate="MACD: %{y:.2f}<extra></extra>", showlegend=False, row=4, col=1)
    fig.add_scatter(x=x, y=df["signal"], name="Signal", mode="lines", line=dict(color=SERIES[1], width=1.5),
                    hovertemplate="Signal: %{y:.2f}<extra></extra>", showlegend=False, row=4, col=1)

    right = 150 if (sr is not None and "Support / resistance" in overlays) else 8
    fig.update_layout(height=height, margin=dict(l=8, r=right, t=30, b=8), hovermode="x unified", bargap=0.1,
                      legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="left", x=0),
                      xaxis_rangeslider_visible=False,
                      font=dict(family='system-ui, -apple-system, "Segoe UI", sans-serif'))
    fig.update_xaxes(showgrid=False, rangebreaks=[dict(bounds=["sat", "mon"])])
    fig.update_yaxes(showgrid=True, gridcolor=GRID, zeroline=False)
    fig.update_yaxes(tickprefix="$", row=1, col=1)
    fig.update_yaxes(title_text="Volume", title_font=dict(size=10), row=2, col=1)
    fig.update_yaxes(title_text="RSI", title_font=dict(size=10), range=[0, 100], tickvals=[30, 70], row=3, col=1)
    fig.update_yaxes(title_text="MACD", title_font=dict(size=10), row=4, col=1)
    return fig


def relative_performance(df: pd.DataFrame, stock: str, height: int = 340) -> go.Figure:
    """Rebased to 100: stock in blue, SPY in gray, sector ETF in orange."""
    fig = go.Figure()
    for i, col in enumerate(df.columns):
        color = SERIES[0] if col == stock else (GRAY if i == 1 else SERIES[1])
        fig.add_scatter(x=df.index, y=df[col], name=col, mode="lines", line=dict(color=color, width=2),
                        hovertemplate=f"{col}: %{{y:.1f}}<extra></extra>")
        fig.add_annotation(x=df.index[-1], y=df[col].iloc[-1], text=f"{col} {df[col].iloc[-1] - 100:+.1f}%",
                           showarrow=False, xanchor="left", xshift=6, font=dict(size=11, color=GRAY))
    fig.add_hline(y=100, line=dict(color=GRAY, width=1))
    _layout(fig, height=height)
    fig.update_xaxes(type="date")
    fig.update_layout(margin=dict(r=110))
    return fig


def drawdown_chart(dd: pd.Series, height: int = 260) -> go.Figure:
    fig = go.Figure(go.Scatter(x=dd.index, y=dd, mode="lines", fill="tozeroy", line=dict(color=BAD, width=1.5),
                               fillcolor="rgba(208,59,59,0.15)", name="Drawdown",
                               hovertemplate="%{x|%d %b %Y}: %{y:.1%} below the previous peak<extra></extra>"))
    _layout(fig, height=height, legend=False, tickformat=".0%")
    fig.update_xaxes(type="date")
    fig.update_layout(hovermode="x")
    return fig


def monthly_heatmap(m: pd.DataFrame, height: int = 300) -> go.Figure:
    """Diverging colors: red (down) - neutral gray (0) - green (up), symmetric scale; values shown in cells."""
    z = m.values.astype(float)
    lim = float(np.nanpercentile(np.abs(z), 95)) if np.isfinite(z).any() else 0.1
    lim = max(lim, 0.01)
    text = [[("" if np.isnan(v) else f"{v * 100:+.1f}%") for v in row] for row in z]
    fig = go.Figure(go.Heatmap(z=z, x=list(m.columns), y=[str(y) for y in m.index], zmin=-lim, zmax=lim,
                               colorscale=[[0, BAD], [0.5, "#e1e0d9"], [1, GOOD]], text=text, texttemplate="%{text}",
                               textfont=dict(size=11), xgap=2, ygap=2, showscale=False,
                               hovertemplate="%{y} %{x}: %{text}<extra></extra>"))
    fig.update_layout(height=height, margin=dict(l=8, r=8, t=10, b=8),
                      font=dict(family='system-ui, -apple-system, "Segoe UI", sans-serif'))
    fig.update_yaxes(type="category", autorange="reversed")
    fig.update_xaxes(side="top")
    return fig


def bars_with_line(x: list[str], bar_series: list[tuple[str, list]], line_name: str, line_vals: list,
                   height: int = 340) -> go.Figure:
    """Money bars plus a money line on the SAME axis (e.g. cash, debt and net debt)."""
    div, suf = money_scale([v for _, vals in bar_series for v in vals] + list(line_vals))
    sc = lambda vals: [None if v is None or pd.isna(v) else v / div for v in vals]  # noqa: E731
    fig = go.Figure()
    for i, (name, vals) in enumerate(bar_series):
        fig.add_bar(x=x, y=sc(vals), name=name, marker_color=SERIES[i], hovertemplate=_hover(name, "money", suf))
    fig.add_scatter(x=x, y=sc(line_vals), name=line_name, mode="lines+markers",
                    line=dict(color=GRAY, width=2), marker=dict(size=8), hovertemplate=_hover(line_name, "money", suf))
    return _layout(fig, height=height, tickprefix="$", ticksuffix=suf)
