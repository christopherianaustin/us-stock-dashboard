"""Tab 1: Summary - scorecard radar, strengths & risks, key stats, mini chart, analysts' view."""
from __future__ import annotations

import html
from typing import Optional

import pandas as pd
import streamlit as st

from app.components import charts, ui
from core import plain_language as pl
from core.glossary import tooltip
from core.i18n import t
from core.models import DataPoint, LicenseTag, Source
from core.scorecard import PILLARS, Scorecard, insight_texts, scoring_config

PILL_CSS = {"strong": "strong", "neutral": "neutral", "weak": "weak"}


def pillar_label(sc_pillar, lang: str) -> str:
    txt = insight_texts(lang)
    name = txt["pillars"][sc_pillar.pillar]
    lv = sc_pillar.level
    word = txt["levels"]["na"] if lv is None else txt["levels"][lv]
    return f"{name} · {word}"


def _fmt_fact(metric: str, v: Optional[float]) -> str:
    if v is None:
        return "—"
    if metric in ("pe_vs_history", "pe_vs_peers", "ev_ebitda_vs_peers", "yield_vs_5y_avg", "peg", "debt_to_equity",
                  "current_ratio", "interest_coverage", "net_debt_to_ebitda", "cash_conversion"):
        return f"{v:.2f}x"
    if metric in ("altman_z", "piotroski"):
        return f"{v:.2f}" if metric == "altman_z" else f"{v:.1f} / 9"
    if metric == "growth_streak":
        return f"{v:.0f} years"
    return f"{v * 100:+.1f}%" if metric in ("revenue_yoy", "eps_yoy", "net_margin_change", "vs_sma50", "vs_sma200",
                                            "rel_strength_6m", "from_52w_high", "estimate_change_90d") \
        else f"{v * 100:.1f}%"


def _scorecard(sc: Scorecard, lang: str) -> None:
    txt = insight_texts(lang)
    st.markdown(f"#### {t('summary.scorecard', lang)}", help=t("summary.scorecard_help", lang))
    if ui.safe_mode():
        st.caption(t("summary.safe_note", lang))
    c1, c2 = st.columns([1.1, 1])
    with c1:
        scored = [p for p in PILLARS if sc.pillars[p].score is not None]
        if len(scored) >= 3:
            st.plotly_chart(charts.radar([txt["pillars"][p] for p in scored], [sc.pillars[p].score for p in scored]),
                            key="summary_radar", config={"displayModeBar": False})
        else:
            st.caption("Radar: not enough scored categories.")
    with c2:
        for p in PILLARS:
            ps = sc.pillars[p]
            css = PILL_CSS.get(ps.level, "na")
            score = f"<span class='pill-score'>{ps.score:.0f}/100</span>" if ps.score is not None else ""
            if ps.level == "not_applicable":
                note = txt["levels"]["not_applicable"]
            elif ps.level is None:
                note = txt["levels"]["na"]
            else:
                note = txt["based_on"].format(n=ps.used, total=ps.total)
            st.markdown(f"<span class='pill {css}'>{html.escape(pillar_label(ps, lang))}{score}</span>"
                        f"<span class='subtle'>{html.escape(note)}</span>", unsafe_allow_html=True,
                        help=txt["pillar_help"][p])
    with st.expander(t("summary.details", lang)):
        cfg = scoring_config()["pillars"]
        rows = []
        for p in PILLARS:
            for d in sc.pillars[p].details:
                m = cfg[p]["metrics"][d["metric"]]
                rows.append({"category": txt["pillars"][p], t("summary.metric", lang): txt["metrics"][d["metric"]],
                             t("summary.value", lang): _fmt_fact(d["metric"], d["value"]),
                             t("summary.points", lang): "—" if d["points"] is None else f"{d['points']:.0f}",
                             "rule": f"{'higher' if m['rule'] == 'higher_better' else 'lower'} is better "
                                     f"({m['range'][0]} → {m['range'][1]})"})
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        st.caption("Thresholds are in config/scoring.yaml. '—' = not available for this company.")


def _insights(sc: Scorecard, lang: str) -> None:
    txt = insight_texts(lang)
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f"#### ✅ {t('summary.strengths', lang)}")
        for i in sc.strengths or []:
            st.markdown(f"- {i.text}")
        if not sc.strengths:
            st.caption(txt["none_strengths"])
    with c2:
        st.markdown(f"#### ⚠️ {t('summary.risks', lang)}")
        for i in sc.risks or []:
            st.markdown(f"- {i.text}")
        if not sc.risks:
            st.caption(txt["none_risks"])
    st.caption(t("summary.insights_note", lang))


def _key_stats(analysis, price, dividends, lang: str) -> None:
    st.markdown(f"#### {t('summary.key_stats', lang)}")
    if analysis is None:
        st.caption("N/A (financial data unavailable)")
        return
    s, med = analysis.snapshot, analysis.peer_medians
    # (label, DataPoint, unit, glossary, peer key, lower_is_better)
    items = [("P/E (TTM)", s["pe"], "x", "pe", "pe", True), ("P/S", s["ps"], "x", "ps", "ps", True),
             ("EV/EBITDA", s["ev_ebitda"], "x", "ev_ebitda", "ev_ebitda", True),
             ("Revenue growth YoY", s["revenue_yoy"], "ratio", "growth", "revenue_growth", False),
             ("Net margin", s["net_margin"], "ratio", "margins", "net_margin", False),
             ("ROE", s["roe"], "ratio", "roe", "roe", False),
             ("Debt to equity", s["debt_to_equity"], "x", "debt_to_equity", None, True)]
    if dividends is not None and dividends.summary.pays and dividends.summary.yield_ttm is not None:
        items.append(("Dividend yield", DataPoint(value=dividends.summary.yield_ttm, source=Source.YFINANCE,
                                                  license_tag=LicenseTag.DEMO_ONLY), "ratio", "dividend_yield", None, False))
    else:
        items.append(("Dividend yield", DataPoint.na("No dividend"), "ratio", "dividend_yield", None, False))
    beta = price.risk.beta if price is not None else None
    items.append(("Beta", DataPoint(value=beta, source=Source.CALCULATED, license_tag=LicenseTag.DEMO_ONLY)
                  if beta is not None else DataPoint.na("Needs price history"), "x", "beta", None, False))
    cols = st.columns(5)
    for i, (label, dp, unit, gkey, peer_key, lower_better) in enumerate(items):
        with cols[i % 5]:
            peer = med.get(peer_key) if peer_key else None
            if dp.available and peer is not None and not ui.safe_mode() and not ui.hidden_by_safe_mode(dp):
                diff = dp.value - peer
                d_txt = (f"{diff * 100:+.1f} pp vs peers" if unit == "ratio" else f"{dp.value / peer - 1:+.0%} vs peers")
                help_text = tooltip(gkey, ui.lang()) + f"\n\n**Peer median:** {ui.fmt_unit(peer, unit)}"
                st.metric(label, ui.fmt_unit(dp.value, unit), delta=d_txt,
                          delta_color="inverse" if lower_better else "normal", help=help_text)
                ui.badge(dp)
            else:
                ui.metric_dp(label, dp, unit, gkey)
    st.caption("Green / red compares with the median of similar companies (for P/E, P/S and EV/EBITDA lower = "
               "green). It describes the data, it is not a recommendation.")


def _mini_chart(price, lang: str) -> None:
    st.markdown(f"#### {t('summary.mini_chart', lang)}", help=tooltip("support_resistance", ui.lang()))
    if price is None:
        st.caption("N/A (price history unavailable)")
        return
    dp = DataPoint(value=1, source=Source.CALCULATED, license_tag=price.license_tag)
    if ui.hidden_by_safe_mode(dp):
        st.caption(ui.SAFE_MODE_TEXT)
        return
    close = price.df["Close"]
    close = close[close.index >= close.index[-1] - pd.DateOffset(years=1)]
    sr = price.sr["1y"]
    st.plotly_chart(charts.mini_price(close, sr.nearest_support.price if sr.nearest_support else None,
                                      sr.nearest_resistance.price if sr.nearest_resistance else None),
                    key="summary_mini", config={"displayModeBar": False})
    st.caption("Support and resistance are areas where price reacted before. They are not guarantees.")
    ui.badge(dp)


def _analysts(ownership, analysis, lang: str) -> None:
    st.markdown(f"#### {t('summary.analysts', lang)}", help=tooltip("analyst_ratings", ui.lang()))
    st.caption(t("summary.analysts_note", lang))
    if ui.safe_mode():
        st.caption(ui.SAFE_MODE_TEXT)
        return
    c1, c2 = st.columns(2)
    with c1:
        cs = ownership.consensus if ownership is not None else None
        if cs:
            st.caption(t("summary.consensus", lang))
            st.plotly_chart(charts.consensus_gauge(cs["mean_score"]), key="summary_consensus",
                            config={"displayModeBar": False})
            st.caption(f"{cs['total']} analysts, {cs['month']:%b %Y}.")
        else:
            st.caption("N/A (no analyst ratings)")
    with c2:
        est = analysis.estimates if analysis is not None else None
        if est is not None and est.target_mean and analysis.price:
            st.caption(t("summary.targets", lang))
            st.plotly_chart(charts.fair_value_chart(analysis.price, [("Analysts' targets", est.target_low,
                                                                      est.target_mean, est.target_high)], height=170),
                            key="summary_targets", config={"displayModeBar": False})
            st.caption(f"Low {ui.fmt_money(est.target_low)} · mean {ui.fmt_money(est.target_mean)} · "
                       f"high {ui.fmt_money(est.target_high)}. Opinion, not a forecast.")
        else:
            st.caption("N/A (no analyst price targets)")
    ui.badge(DataPoint(value=1, source=Source.FINNHUB if ownership is not None and ownership.rec_source == "Finnhub"
                       else Source.YFINANCE, license_tag=LicenseTag.DEMO_ONLY, note="Wall Street analysts' ratings"))


def _short_version(sc: Scorecard, name: str, lang: str) -> None:
    """Two plain lists: what looks good, what to watch (from the scorecard rules)."""
    txt = insight_texts(lang)

    def block(title: str, items, css: str, empty: str) -> str:
        if items:
            lis = "".join(f"<li>{html.escape(i.text)}</li>" for i in items[:3])
            body = f"<ul class='nv-list {css}'>{lis}</ul>"
        else:
            body = f"<div class='nv-empty'>{html.escape(empty)}</div>"
        return f"<div class='nv-card'><h4>{html.escape(title)}</h4>{body}</div>"

    st.markdown(
        f"<div class='nv-section-title'>{html.escape(t('overview.short_title', lang))}</div>"
        f"<div class='nv-section-sub'>{html.escape(t('overview.short_sub', lang, name=name))}</div>"
        f"<div class='nv-two'>{block(t('overview.good', lang), sc.strengths, 'good', txt['none_strengths'])}"
        f"{block(t('overview.watch', lang), sc.risks, 'watch', txt['none_risks'])}</div>",
        unsafe_allow_html=True)


def _key_numbers(analysis, price, dividends, is_financial: bool, lang: str) -> None:
    """Six numbers a beginner can read: value, plain label and one everyday sentence."""
    if analysis is None:
        return
    s = analysis.snapshot

    def val(key):
        dp = s.get(key)
        return dp.value if dp is not None and dp.available else None

    cards = []

    def card(label: str, gkey: str, value: str, ex: pl.Explained, hidden: bool = False) -> None:
        tip = ui.attr(tooltip(gkey, ui.lang()))
        if hidden:
            value, tone, label_txt, sentence = "—", "na", ui.SAFE_MODE_TEXT, ""
        else:
            tone, label_txt, sentence = ex.tone, ex.label, ex.sentence
        cards.append(f"<div class='nv-num'><div class='nv-num-label' title='{tip}'>{html.escape(label)} ⓘ</div>"
                     f"<div class='nv-num-value'>{html.escape(value)}</div>"
                     f"<span class='nv-tone {tone}'>{html.escape(label_txt)}</span>"
                     f"<div class='nv-num-text'>{html.escape(sentence)}</div></div>")

    pe = val("pe")
    pe_pct = analysis.stats["pe"].percentile if "pe" in analysis.stats else None
    neg = s.get("pe") is not None and (s["pe"].na_reason or "").startswith("N/A (negative")
    card("Price vs profit (P/E)", "pe", f"{pe:.1f}×" if pe else "—", pl.pe_ratio(pe, pe_pct, lang, neg),
         ui.hidden_by_safe_mode(s["pe"]))
    g = val("revenue_yoy")
    card("Sales growth vs last year", "growth", f"{g * 100:+.1f}%" if g is not None else "—", pl.revenue_growth(g, lang))
    m = val("net_margin")
    card("Profit margin", "margins", f"{m * 100:.1f}%" if m is not None else "—", pl.net_margin(m, lang))
    de = val("debt_to_equity")
    card("Debt vs owners' money", "debt_to_equity", f"{de:.2f}×" if de is not None and not is_financial else "—",
         pl.debt_to_equity(de, lang, is_financial))
    pays = dividends is not None and dividends.summary.pays
    y = dividends.summary.yield_ttm if pays else None
    card("Dividend yield", "dividend_yield", f"{y * 100:.2f}%" if y is not None else "—",
         pl.dividend_yield(y, pays, lang), ui.safe_mode())
    b = price.risk.beta if price is not None else None
    card("Ups and downs vs the market", "beta", f"{b:.2f}" if b is not None else "—", pl.beta(b, lang), ui.safe_mode())

    st.markdown(
        f"<div class='nv-section-title'>{html.escape(t('overview.numbers_title', lang))}</div>"
        f"<div class='nv-section-sub'>{html.escape(t('overview.numbers_sub', lang))}</div>"
        f"<div class='nv-grid'>{''.join(cards)}</div>"
        f"<div class='nv-note'>{html.escape(t('overview.numbers_note', lang))}</div>",
        unsafe_allow_html=True)


def render_summary_tab(sc: Optional[Scorecard], analysis, price, dividends, ownership, header=None) -> None:
    lang = ui.lang()
    if sc is None:
        st.info("The scorecard needs financial data, which is not available for this company.")
        return
    if header is None:
        name = "this company"
    elif header.profile.display_name.available and not ui.safe_mode():
        name = str(header.profile.display_name.value)
    else:
        name = str(header.profile.name.value or header.symbol)
    is_fin = bool(header.profile.is_financial_company) if header is not None else False
    _short_version(sc, name, lang)
    _key_numbers(analysis, price, dividends, is_fin, lang)

    st.markdown(f"<div class='nv-section-title'>{html.escape(t('overview.more_title', lang))}</div>",
                unsafe_allow_html=True)
    _scorecard(sc, lang)
    with st.expander("Compared with similar companies"):
        _key_stats(analysis, price, dividends, lang)
    c1, c2 = st.columns([1.2, 1])
    with c1:
        _mini_chart(price, lang)
    with c2:
        _analysts(ownership, analysis, lang)
