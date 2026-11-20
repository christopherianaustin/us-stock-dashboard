"""Always-visible header: who the company is, today's price in big type, three simple facts,
the category read (pills) and how fresh the financial data is."""
from __future__ import annotations

import html
import re
from datetime import date
from typing import Optional

import streamlit as st

from app.components import ui
from app.components.summary_tab import pillar_label
from core.glossary import tooltip
from core.i18n import t
from core.models import HeaderData
from core.scorecard import PILLARS as SC_PILLARS
from core.scorecard import Scorecard, insight_texts


def _first_sentence(text: str, limit: int = 220) -> str:
    s = re.split(r"(?<=[.!?])\s+", text.strip())[0]
    return s if len(s) <= limit else s[:limit].rsplit(" ", 1)[0] + "…"


def _shown(dp) -> bool:
    return dp.available and not ui.hidden_by_safe_mode(dp)


def _identity(h: HeaderData) -> str:
    p = h.profile
    name_dp = p.display_name if _shown(p.display_name) else p.name
    name = html.escape(str(name_dp.value)) if name_dp.available else html.escape(h.symbol)
    if _shown(p.logo_url):
        logo = f"<img class='nv-logo' src='{html.escape(p.logo_url.value)}' alt='{name} logo'>"
    else:
        logo = f"<div class='nv-logo nv-initials' aria-hidden='true'>{html.escape(h.symbol[:2])}</div>"
    meta = " · ".join(html.escape(str(dp.value)) for dp in (p.exchange, p.sector, p.industry) if _shown(dp))
    about = ""
    if _shown(p.description):
        about = f"<div class='nv-about'>{html.escape(_first_sentence(p.description.value))}</div>"
    return (f"<div><div class='nv-id'>{logo}<div><h1 class='nv-name'>{name}"
            f"<span class='nv-ticker'>{html.escape(h.symbol)}</span></h1>"
            f"<div class='nv-meta'>{meta}</div></div></div>{about}</div>")


def _price(h: HeaderData) -> str:
    if ui.hidden_by_safe_mode(h.price):
        return f"<div class='nv-pricebox'><div class='nv-asof'>{ui.SAFE_MODE_TEXT}</div></div>"
    if not h.price.available:
        return f"<div class='nv-pricebox'><div class='nv-asof'>Price not available right now</div></div>"
    price = f"<div class='nv-price'>{ui.fmt_money(h.price.value)}</div>"
    chg = ""
    if h.change.available and h.change_pct.available:
        c, pct = h.change.value, h.change_pct.value
        cls, arrow, word = ("up", "▲", "up") if c > 0 else (("down", "▼", "down") if c < 0 else ("flat", "", "unchanged"))
        chg = (f"<div class='nv-change {cls}' aria-label='{word} today'>{arrow} {ui.fmt_money(abs(c))} "
               f"({abs(pct) * 100:.2f}%) {word} today</div>")
    return (f"<div class='nv-pricebox'>{price}{chg}"
            f"<div class='nv-asof'>US dollars · price may be delayed</div></div>")


def _stat(label: str, help_key: str, value: str, sub: str = "", extra: str = "") -> str:
    tip = ui.attr(tooltip(help_key, ui.lang()))
    sub_html = f"<div class='nv-stat-sub'>{sub}</div>" if sub else ""
    return (f"<div class='nv-stat'><div class='nv-stat-label' title='{tip}'>{html.escape(label)} ⓘ</div>"
            f"<div class='nv-stat-value'>{value}</div>{extra}{sub_html}</div>")


def _stats(h: HeaderData) -> str:
    cells = []
    mc = h.market_cap
    cells.append(_stat("Company value (market cap)", "market_cap",
                       ui.fmt_big_money(mc.value) if _shown(mc) else "—",
                       "" if _shown(mc) else (ui.SAFE_MODE_TEXT if ui.hidden_by_safe_mode(mc) else "Not available")))
    lo, hi, pr = h.week52_low, h.week52_high, h.price
    if _shown(lo) and _shown(hi) and hi.value > lo.value:
        pos = None
        if _shown(pr):
            pos = min(max((pr.value - lo.value) / (hi.value - lo.value), 0.0), 1.0)
        mark = f"<div class='mark' style='left:{pos * 100:.1f}%'></div>" if pos is not None else ""
        bar = (f"<div class='rangebar' role='img' aria-label='Price position within the past year range'>{mark}</div>"
               f"<div class='rangelabels'><span>{ui.fmt_money(lo.value)}</span><span>{ui.fmt_money(hi.value)}</span></div>")
        sub = ""
        if pos is not None:
            from_hi = pr.value / hi.value - 1
            sub = "At its high for the year" if from_hi > -0.005 else f"{abs(from_hi) * 100:.1f}% below the year's high"
        cells.append(_stat("Price range, past year", "week52_range", "", sub, bar))
    else:
        cells.append(_stat("Price range, past year", "week52_range", "—",
                           ui.SAFE_MODE_TEXT if ui.hidden_by_safe_mode(hi) else "Not available"))
    ne = h.next_earnings_date
    if _shown(ne) and isinstance(ne.value, date):
        days = (ne.value - date.today()).days
        cells.append(_stat("Next earnings report", "next_earnings", ne.value.strftime("%d %b %Y"),
                           "today" if days == 0 else f"in {days} days"))
    else:
        cells.append(_stat("Next earnings report", "next_earnings", "—",
                           ui.SAFE_MODE_TEXT if ui.hidden_by_safe_mode(ne) else "Not announced yet"))
    return f"<div class='nv-stats'>{''.join(cells)}</div>"


def _pills(scorecard: Optional[Scorecard]) -> str:
    if scorecard is None:
        return ""
    txt = insight_texts(ui.lang())
    out = []
    for key in SC_PILLARS:
        ps = scorecard.pillars[key]
        css = {"strong": "strong", "neutral": "neutral", "weak": "weak"}.get(ps.level, "na")
        score = f"<span class='pill-score'>{ps.score:.0f}</span>" if ps.score is not None else ""
        out.append(f"<span class='pill {css}' title='{ui.attr(txt['pillar_help'][key])}'>"
                   f"{html.escape(pillar_label(ps, ui.lang()))}{score}</span>")
    label = html.escape(t("header.scorecard", ui.lang()))
    return f"<div class='nv-pills'><span class='nv-pills-label'>{label}</span>{''.join(out)}</div>"


def _freshness(h: HeaderData) -> str:
    fresh = h.data_freshness
    if not fresh.available:
        return f"<div class='nv-fresh'>Financial data: not available ({html.escape(fresh.na_reason or '')})</div>"
    link = ""
    if h.latest_report and (h.latest_report.url or h.latest_report.index_url):
        link = (f" · <a href='{html.escape(h.latest_report.url or h.latest_report.index_url)}' target='_blank' "
                f"rel='noopener'>open the filing</a>")
    tip = ui.attr(tooltip("data_freshness", ui.lang()))
    return f"<div class='nv-fresh' title='{tip}'>{html.escape(fresh.value)}{link} {ui.badge_html(fresh)}</div>"


def render_header(h: HeaderData, scorecard: Optional[Scorecard] = None) -> None:
    for w in h.warnings:
        st.warning(w)
    st.markdown(f"<div class='nv-hero'>{_identity(h)}{_price(h)}</div>{_stats(h)}{_pills(scorecard)}{_freshness(h)}",
                unsafe_allow_html=True)
    # In safe mode / with sources on, show where the header numbers come from
    if ui.show_sources():
        bits = [ui.badge_html(dp) for dp in (h.price, h.market_cap, h.week52_high, h.next_earnings_date)
                if not ui.hidden_by_safe_mode(dp)]
        bits = [b for b in bits if b]
        if bits:
            st.markdown("<div class='nv-fresh'>Sources: " + " ".join(bits) + "</div>", unsafe_allow_html=True)
