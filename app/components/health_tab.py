"""Tab 6: Profitability & Financial Health."""
from __future__ import annotations

from typing import Optional

import pandas as pd
import streamlit as st

from app.components import charts, ui
from core.analysis import Analysis
from core.financials import Financials, period_label
from core.glossary import tooltip
from core.models import DataPoint, LicenseTag, Source
from core.ratios import FINANCIAL_NA, METRICS

PROFIT_CARDS = ["roe", "roa", "roic", "gross_margin", "operating_margin", "net_margin"]
HEALTH_CARDS = ["debt_to_equity", "current_ratio", "quick_ratio", "debt_to_ebitda", "interest_coverage", "net_debt"]
CASH_CARDS = ["fcf_ttm", "fcf_margin", "fcf_per_share", "cash_conversion", "shareholder_returns", "bvps"]
GROWTH_CARDS = ["revenue_yoy", "eps_yoy", "revenue_cagr_3y", "revenue_cagr_5y", "eps_cagr_5y", "fcf_cagr_5y"]


def _calc_badge(fin: Financials) -> None:
    lic = LicenseTag.CALCULATED_SAFE if fin.source == Source.SEC.value else LicenseTag.DEMO_ONLY
    ui.badge(DataPoint(value=1, source=Source.CALCULATED, license_tag=lic, derived=True,
                       note=f"Calculated from {fin.source} financial statements"))


def _card_row(a: Analysis, names: list[str], title: str, help_text: str) -> None:
    st.markdown(f"##### {title}", help=help_text)
    cols = st.columns(len(names))
    for col, name in zip(cols, names):
        label, unit, _, gkey = METRICS[name]
        with col:
            ui.metric_dp(label, a.snapshot[name], unit, gkey)


def _x_labels(fin: Financials, idx: pd.Index) -> list[str]:
    meta = fin.tidy[fin.tidy["period_type"] == "Q"].drop_duplicates("period_end").set_index("period_end")
    out = []
    for pe in idx:
        if pe in meta.index:
            lab = period_label(meta.loc[pe, "fiscal_year"], meta.loc[pe, "fiscal_quarter"], "Q")
        else:
            lab = f"{pe:%b %Y}"
        out.append(f"{lab}<br><span style='font-size:10px'>{pe:%d %b %y}</span>")
    return out


def _trend(a: Analysis, fin: Financials, cols: list[tuple[str, str]], kind: str, key: str, title: str,
           help_key: list[str], n: int = 12) -> None:
    q = a.quarterly
    present = [(lab, c) for lab, c in cols if c in q and q[c].notna().any()
               and not (fin.is_financial and c in FINANCIAL_NA)]
    help_text = "\n\n---\n\n".join(tooltip(k, ui.lang()) for k in help_key)
    st.markdown(f"##### {title}", help=help_text)
    if not present:
        st.caption("N/A (" + (a.snapshot.get(cols[0][1]).na_reason if cols[0][1] in a.snapshot
                               and not a.snapshot[cols[0][1]].available else "not enough data") + ")")
        return
    sub = q[[c for _, c in present]].dropna(how="all").tail(n)
    x = _x_labels(fin, sub.index)
    series = [(lab, [None if pd.isna(v) else float(v) for v in sub[c]]) for lab, c in present]
    fig = charts.lines(x, series, kind=kind, height=300)
    st.plotly_chart(fig, key=f"{a.symbol}_{key}", config={"displayModeBar": False})
    _calc_badge(fin)
    for lab, c in cols:
        if (lab, c) not in present:
            reason = FINANCIAL_NA.get(c) if fin.is_financial else None
            st.caption(f"{lab}: N/A ({reason or 'not enough data'})")


def _dupont(a: Analysis, fin: Financials) -> None:
    st.markdown("##### What drives ROE? (DuPont breakdown)", help=tooltip("dupont", ui.lang()))
    s = a.snapshot
    parts = [s["net_margin"], s["asset_turnover"], s["equity_multiplier"], s["roe"]]
    if all(p.available for p in parts):
        st.markdown(f"**ROE {parts[3].value:.1%}** = net margin **{parts[0].value:.1%}** × asset turnover "
                    f"**{parts[1].value:.2f}x** × equity multiplier **{parts[2].value:.2f}x**")
        lev_share = "mostly from leverage (debt / small equity)" if parts[2].value > 4 else \
            "mostly from profitability and efficiency"
        st.caption(f"This company's ROE comes {lev_share}.")
    else:
        st.caption("N/A (needs net income, revenue, assets and positive equity)")
        return
    q = a.quarterly
    sub = q[["net_margin_ttm", "asset_turnover", "equity_multiplier"]].dropna(how="all").tail(12)
    x = _x_labels(fin, sub.index)
    c1, c2, c3 = st.columns(3)
    for col, (lab, c, kind) in zip((c1, c2, c3), (("Net margin", "net_margin_ttm", "pct"),
                                                  ("Asset turnover", "asset_turnover", "x"),
                                                  ("Equity multiplier", "equity_multiplier", "x"))):
        with col:
            vals = [None if pd.isna(v) else float(v) for v in sub[c]]
            st.caption(lab)
            st.plotly_chart(charts.lines(x, [(lab, vals)], kind=kind, height=220), key=f"{a.symbol}_dupont_{c}",
                            config={"displayModeBar": False})
    _calc_badge(fin)


def _piotroski(a: Analysis, fin: Financials) -> None:
    p = a.piotroski
    st.markdown("##### Piotroski F-score (financial strength checklist)", help=tooltip("piotroski", ui.lang()))
    if p.tested == 0:
        st.caption(f"N/A ({p.reason or 'not enough annual data'})")
        return
    level = "Strong" if p.score >= 7 else ("Average" if p.score >= 4 else "Weak")
    icon = {"Strong": "🟢", "Average": "🟡", "Weak": "🔴"}[level]
    st.markdown(f"### {icon} {p.score} / 9 · {level}")
    st.caption(f"FY{p.fiscal_year} vs the year before. Based on {p.tested} of 9 tests that could be calculated"
               + (" (banks and insurers lack some inputs)." if p.tested < 9 else "."))
    lines = []
    for c in p.checks:
        mark = "✅" if c.passed else ("❌" if c.passed is False else "➖")
        lines.append(f"{mark} **{c.name}** — {c.explanation} <span style='opacity:.7'>({c.detail})</span>")
    st.markdown("<br>".join(lines), unsafe_allow_html=True)
    _calc_badge(fin)


def _altman(a: Analysis, fin: Financials) -> None:
    z = a.altman
    st.markdown("##### Altman Z-score (financial distress risk)", help=tooltip("altman", ui.lang()))
    if z.z is None:
        st.caption(f"N/A ({z.reason})")
        return
    if ui.safe_mode():
        st.caption(f"{ui.SAFE_MODE_TEXT} (the Altman Z-score uses market cap, which needs a licensed price).")
        return
    zones = [(0, 1.81, charts.STATUS_CRIT), (1.81, 2.99, charts.STATUS_WARN), (2.99, 6, charts.STATUS_GOOD)]
    st.plotly_chart(charts.zone_gauge(z.z, zones, 6, "Z-score (scale capped at 6)"), key=f"{a.symbol}_altman",
                    config={"displayModeBar": False})
    icon = {"Safe": "🟢", "Grey": "🟡", "Distress": "🔴"}[z.zone]
    st.markdown(f"{icon} **{z.zone} zone** (safe > 2.99 · grey 1.81–2.99 · distress < 1.81)")
    lic = LicenseTag.DEMO_ONLY  # uses market cap, which uses the demo price
    ui.badge(DataPoint(value=1, source=Source.CALCULATED, license_tag=lic, derived=True,
                       note="Uses market cap (price x shares), so it follows the price source"))


def render_health_tab(a: Optional[Analysis], fin: Optional[Financials]) -> None:
    if a is None or fin is None:
        st.info("Profitability and financial health need financial statements, which are not available.")
        return
    if ui.safe_mode() and fin.source != Source.SEC.value:
        st.info(ui.SAFE_MODE_TEXT)
        return
    _card_row(a, PROFIT_CARDS, "Profitability (last 12 months)", tooltip("roe", ui.lang()))
    _card_row(a, GROWTH_CARDS, "Growth", tooltip("cagr", ui.lang()))
    _card_row(a, HEALTH_CARDS, "Financial health (latest quarter)", tooltip("debt_to_equity", ui.lang()))
    _card_row(a, CASH_CARDS, "Cash flow (last 12 months)", tooltip("fcf", ui.lang()))
    st.divider()
    _trend(a, fin, [("ROE", "roe"), ("ROA", "roa"), ("ROIC", "roic")], "pct", "returns",
           "Returns on capital (TTM): higher means each dollar invested earns more", ["roe", "roa", "roic"])
    _dupont(a, fin)
    st.divider()
    c1, c2 = st.columns(2)
    with c1:
        _piotroski(a, fin)
    with c2:
        _altman(a, fin)
    st.divider()
    c1, c2 = st.columns(2)
    with c1:
        _trend(a, fin, [("Interest coverage", "interest_coverage")], "x", "intcov",
               "Interest coverage: how easily profit pays the interest", ["interest_coverage"])
    with c2:
        _trend(a, fin, [("Debt to EBITDA", "debt_to_ebitda")], "x", "debt_ebitda",
               "Debt to EBITDA: years of cash profit needed to repay debt", ["debt_to_ebitda"])
