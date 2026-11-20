"""Always-visible header: identity, price, market cap, 52-week range, next earnings, scorecard, freshness."""
from __future__ import annotations

import html
from datetime import date

import streamlit as st

from app.components import ui
from core.glossary import label as g_label
from core.glossary import tooltip
from typing import Optional

from app.components.summary_tab import pillar_label
from core.i18n import t
from core.models import HeaderData
from core.scorecard import PILLARS as SC_PILLARS
from core.scorecard import Scorecard, insight_texts

def render_header(h: HeaderData, scorecard: Optional[Scorecard] = None) -> None:
    p = h.profile
    for w in h.warnings:
        st.warning(w, icon="⚠️")

    # ----- identity row -----
    logo_col, id_col = st.columns([1, 11], vertical_alignment="center")
    with logo_col:
        if p.logo_url.available and not ui.hidden_by_safe_mode(p.logo_url):
            st.image(p.logo_url.value, width=56)
        else:
            st.markdown(f"<div style='font-size:2rem;font-weight:700;opacity:.5'>{html.escape(h.symbol[:2])}</div>",
                        unsafe_allow_html=True)
    with id_col:
        # Prefer the nicely-cased name unless safe mode hides demo data
        name_dp = p.display_name if (p.display_name.available and not ui.hidden_by_safe_mode(p.display_name)) else p.name
        name = ui.text_value(name_dp)
        st.markdown(f"<h2 style='margin:0;padding:0'>{name} {ui.dot_html(name_dp)} "
                    f"<span style='opacity:.6;font-weight:500'>({html.escape(h.symbol)})</span></h2>",
                    unsafe_allow_html=True)
        bits = []
        for dp in (p.exchange, p.sector, p.industry):
            if dp.available or ui.hidden_by_safe_mode(dp):
                bits.append(f"{ui.text_value(dp)}{ui.dot_html(dp)}")
        st.markdown(f"<div class='subtle'>{' &nbsp;·&nbsp; '.join(bits)}</div>", unsafe_allow_html=True)

    # ----- metrics row -----
    c1, c2, c3, c4 = st.columns([1.1, 1.1, 1.6, 1.2])
    with c1:
        delta = None
        if h.change.available and h.change_pct.available and not ui.hidden_by_safe_mode(h.change):
            delta = f"{h.change.value:+.2f} ({ui.fmt_pct(h.change_pct.value)}) today"
        ui.metric("price", h.price, ui.fmt_money, delta=delta)
    with c2:
        ui.metric("market_cap", h.market_cap, ui.fmt_big_money)
    with c3:
        _range_bar(h)
    with c4:
        _next_earnings(h)

    # ----- scorecard pills + freshness -----
    if scorecard is not None:
        txt = insight_texts(ui.lang())
        pills = []
        for p in SC_PILLARS:
            ps = scorecard.pillars[p]
            css = {"strong": "strong", "neutral": "neutral", "weak": "weak"}.get(ps.level, "na")
            score = f" {ps.score:.0f}" if ps.score is not None else ""
            tip = html.escape(txt["pillar_help"][p])
            pills.append(f"<span class='pill {css}' title='{tip}'>{html.escape(pillar_label(ps, ui.lang()))}{score}</span>")
        st.markdown(f"<div style='margin-top:4px'><span class='subtle' style='margin-right:6px'>"
                    f"{html.escape(t('header.scorecard', ui.lang()))}:</span>{''.join(pills)}</div>",
                    unsafe_allow_html=True)
    fresh = h.data_freshness
    if fresh.available:
        link = ""
        if h.latest_report and (h.latest_report.url or h.latest_report.index_url):
            link = f" &nbsp;<a href='{h.latest_report.url or h.latest_report.index_url}' target='_blank'>open filing ↗</a>"
        st.markdown(f"<div class='subtle' style='margin-top:6px' title='{html.escape(tooltip('data_freshness', ui.lang()))}'>"
                    f"🗓️ {html.escape(fresh.value)} {ui.badge_html(fresh)}{link}</div>", unsafe_allow_html=True)
    else:
        st.caption(f"🗓️ Data freshness: N/A ({fresh.na_reason})")


def _range_bar(h: HeaderData) -> None:
    title = g_label("week52_range", ui.lang())
    tip = html.escape(tooltip("week52_range", ui.lang()))
    lo, hi, price = h.week52_low, h.week52_high, h.price
    st.markdown(f"<div style='font-size:0.875rem' title='{tip}'>{title} ⓘ</div>", unsafe_allow_html=True)
    if any(ui.hidden_by_safe_mode(x) for x in (lo, hi)):
        st.caption(ui.SAFE_MODE_TEXT)
        return
    if not (lo.available and hi.available) or hi.value <= lo.value:
        st.caption(f"N/A ({lo.na_reason or hi.na_reason or 'price history unavailable'})")
        return
    pos = None
    if price.available:
        pos = min(max((price.value - lo.value) / (hi.value - lo.value), 0.0), 1.0)
    mark = f"<div class='mark' style='left:{pos * 100:.1f}%'></div>" if pos is not None else ""
    st.markdown(
        f"<div class='rangebar'>{mark}</div>"
        f"<div class='rangelabels'><span>Low {ui.fmt_money(lo.value)}</span><span>High {ui.fmt_money(hi.value)}</span></div>",
        unsafe_allow_html=True)
    if pos is not None:
        from_hi = price.value / hi.value - 1
        from_lo = price.value / lo.value - 1
        st.caption(f"{from_hi * 100:+.1f}% from high · {from_lo * 100:+.1f}% from low")
    st.markdown(ui.badge_html(hi), unsafe_allow_html=True)


def _next_earnings(h: HeaderData) -> None:
    dp = h.next_earnings_date
    delta = None
    if dp.available and isinstance(dp.value, date):
        days = (dp.value - date.today()).days
        delta = "today" if days == 0 else f"in {days} days"
    ui.metric("next_earnings", dp, lambda d: d.strftime("%b %d, %Y"), delta=delta, delta_color="off")
