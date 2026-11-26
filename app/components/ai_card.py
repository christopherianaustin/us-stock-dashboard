"""AI Insight card at the top of each tab: Bullish and Bearish lists side by side (SPEC 16.5).

Flow per tab: a skeleton is drawn at the top first, the rest of the tab renders below it, then the summary is
fetched (cache -> AI -> checks -> rule-based fallback, see core/ai_summary/service.py) and replaces the skeleton.
If anything fails, the card quietly disappears: the tab itself never breaks because of AI.
"""
from __future__ import annotations

import html
import time
from typing import Optional

import streamlit as st

from app.components import ui
from config.settings import settings
from core.logging_setup import get_logger

log = get_logger("ai_card")

# Streamlit tab key -> AI tab (core/ai_summary/input_builder.TABS). The Coverage tab has no AI card.
AI_TAB = {"summary": "summary", "price": "price_technicals", "earnings": "earnings", "financials": "financials",
          "valuation": "valuation", "health": "profitability_health", "dividends": "dividends",
          "ownership": "ownership_sentiment", "news": "news_filings", "profile": "company_profile"}

TXT = {
    "en": {"label": "AI Insight", "auto": "Automatic summary", "writing": "Writing the AI Insight…",
           "bull": "Bullish", "bear": "Bearish",
           "bull_help": "Bullish = points that support a positive view",
           "bear_help": "Bearish = points that support a negative view or are risks",
           "bull_empty": "No clear bullish points in this tab's data.",
           "bear_empty": "No major bearish points in this tab's data. Check the other tabs too.",
           "gaps": "Data gaps",
           "footer": "AI-generated from the data on this page (as of {date}). It can make mistakes and is not "
                     "investment advice.",
           "auto_footer": "Automatic summary from our rule-based checks (as of {date}). Not investment advice.",
           "thanks": "Thanks for the feedback."},
    "id": {"label": "Insight AI", "auto": "Ringkasan otomatis", "writing": "Sedang menulis Insight AI…",
           "bull": "Bullish", "bear": "Bearish",
           "bull_help": "Bullish = poin yang mendukung pandangan positif",
           "bear_help": "Bearish = poin yang mendukung pandangan negatif atau risiko",
           "bull_empty": "Tidak ada poin bullish yang jelas di data tab ini.",
           "bear_empty": "Tidak ada poin bearish utama di data tab ini. Periksa juga tab lainnya.",
           "gaps": "Data yang kurang",
           "footer": "Dibuat oleh AI dari data di halaman ini (per {date}). Bisa keliru dan bukan saran investasi.",
           "auto_footer": "Ringkasan otomatis dari pemeriksaan berbasis aturan kami (per {date}). Bukan saran investasi.",
           "thanks": "Terima kasih atas masukannya."},
}

UP = ("<svg width='18' height='18' viewBox='0 0 24 24' aria-hidden='true'><circle cx='12' cy='12' r='12' fill='#E6F4EA'/>"
      "<path d='M12 17V7M7.5 11.5 12 7l4.5 4.5' stroke='#1e8e4e' stroke-width='2.2' fill='none' stroke-linecap='round' "
      "stroke-linejoin='round'/></svg>")
DOWN = ("<svg width='18' height='18' viewBox='0 0 24 24' aria-hidden='true'><circle cx='12' cy='12' r='12' fill='#FCE8E6'/>"
        "<path d='M12 7v10M7.5 12.5 12 17l4.5-4.5' stroke='#C4302B' stroke-width='2.2' fill='none' stroke-linecap='round' "
        "stroke-linejoin='round'/></svg>")

CSS = """<style>
.ai-label {font-size:0.8125rem;font-weight:600;color:#6E3FD1;letter-spacing:.01em}
.ai-side {display:flex;align-items:center;gap:8px;font-size:1rem;font-weight:600;color:#1D1D1F}
.ai-help {font-size:0.75rem;line-height:1.1rem;color:#86868B;margin:2px 0 8px}
.ai-pts {list-style:none;padding:0;margin:0}
.ai-pts li {font-size:0.9375rem;line-height:1.375rem;color:#424245;margin:0 0 10px;text-wrap:pretty}
.ai-pts li b {display:block;color:#1D1D1F;font-weight:600}
.ai-empty {font-size:0.875rem;color:#6E6E73;margin:0}
.ai-foot {font-size:0.75rem;line-height:1.1rem;color:#86868B;margin-top:4px}
.ai-skel {border-radius:12px;padding:16px;background:#F5F5F7;margin-bottom:8px}
.ai-skel div {height:12px;border-radius:6px;margin:8px 0;
  background:linear-gradient(90deg,#E5E5EA 25%,#F0F0F3 50%,#E5E5EA 75%);background-size:200% 100%;
  animation:aiShimmer 1.2s ease-in-out infinite}
@keyframes aiShimmer {0%{background-position:200% 0}100%{background-position:-200% 0}}
@media (prefers-reduced-motion: reduce) {.ai-skel div {animation:none}}
</style>"""


def enabled() -> bool:
    """AI_SUMMARIES_ENABLED=false or no ANTHROPIC_API_KEY: no cards at all."""
    return settings.ai_enabled


def start(tab_key: str):
    """Call at the top of a tab: draws the skeleton and returns the placeholder to fill later (or None)."""
    if not enabled() or tab_key not in AI_TAB:
        return None
    ph = st.empty()
    lang = ui.lang()
    ph.markdown(CSS + f"<div class='ai-skel' role='status' aria-label='{TXT[lang]['writing']}'>"
                f"<span class='ai-label'>✨ {TXT[lang]['writing']}</span>"
                "<div style='width:55%'></div><div style='width:95%'></div><div style='width:80%'></div></div>",
                unsafe_allow_html=True)
    return ph


def _fetch(bundle, tab: str, lang: str, safe: bool) -> Optional[dict]:
    """Same path as the API endpoint, in-process. The Streamlit bundle is handed to the API module so the data
    is not loaded twice."""
    import api.main as api
    from core.ai_summary.service import get_summary

    with api._lock:
        api._cache[bundle.resolved.symbol] = (time.time(), bundle)
    _, ti = api.ai_tab_input(bundle.resolved.symbol, tab, lang, "USD", safe)
    return get_summary(bundle.resolved.symbol, tab, lang, "USD", ti)


def _date(as_of: Optional[str]) -> str:
    return str(as_of or "")[:10] or "-"


def _side(items: list, kind: str, x: dict) -> str:
    """One block: icon + name, helper text, then the points (title in bold, then the detail) or the empty message.
    AI points are {title, detail}; automatic-summary points are plain sentences."""
    head = (f"<div class='ai-side'>{UP if kind == 'bull' else DOWN}{x[kind]}</div>"
            f"<div class='ai-help'>{x[kind + '_help']}</div>")
    if not items:
        return head + f"<p class='ai-empty'>{x[kind + '_empty']}</p>"
    rows = "".join(f"<li><b>{html.escape(p['title'])}</b>{html.escape(p['detail'])}</li>" if isinstance(p, dict)
                   else f"<li>{html.escape(p)}</li>" for p in items)
    return head + f"<ul class='ai-pts'>{rows}</ul>"


def _save_vote(key: str, res: dict, lang: str) -> None:
    """Save a thumbs up / down once per card (the vote itself lives in the widget's session state)."""
    from core.ai_summary.service import save_feedback

    v = st.session_state.get(key)
    if v is None or st.session_state.get(key + "|saved") == v:
        return
    try:
        save_feedback(res["ticker"], res["tab"], lang, res.get("prompt_version", ""), "up" if v == 1 else "down",
                      source=res.get("source", "ai"), surface="streamlit")
        st.session_state[key + "|saved"] = v
    except Exception:  # noqa: BLE001 - feedback must never break the page
        log.exception("Could not save AI feedback")


def finish(ph, tab_key: str, bundle) -> None:
    """Fill the placeholder from start() with the card, or remove it quietly."""
    if ph is None:
        return
    lang, safe = ui.lang(), ui.safe_mode()
    t0 = time.perf_counter()
    try:
        res = _fetch(bundle, AI_TAB[tab_key], lang, safe)
    except Exception:  # noqa: BLE001 - no AI card is better than a broken tab
        log.exception("AI Insight failed for %s %s", bundle.resolved.symbol, tab_key)
        ph.empty()
        return
    log.info("timing | ai %s %.2fs (%s%s)", tab_key, time.perf_counter() - t0, (res or {}).get("source"),
             ", cached" if (res or {}).get("cached") else "")
    if not res or not res.get("enabled"):
        ph.empty()
        return
    s, x = res["summary"], TXT[lang]
    ai = res["source"] == "ai"
    if not ai and not (s["bullish"] or s["bearish"]):
        ph.empty()            # nothing to show: hide rather than show an empty box
        return
    date = _date(res.get("as_of"))
    with ph.container(border=True):
        st.markdown(CSS + f"<span class='ai-label'>{'✨ ' + x['label'] if ai else x['auto']}</span>",
                    unsafe_allow_html=True)
        left, right = st.columns(2, gap="large")      # side by side on desktop (Streamlit stacks them on phones)
        left.markdown(_side(s["bullish"], "bull", x), unsafe_allow_html=True)
        right.markdown(_side(s["bearish"], "bear", x), unsafe_allow_html=True)
        if ai and s.get("data_gaps"):
            st.caption(f"{x['gaps']}: " + " · ".join(s["data_gaps"]))
        st.markdown(f"<div class='ai-foot'>{html.escape((x['footer'] if ai else x['auto_footer']).format(date=date))}"
                    "</div>", unsafe_allow_html=True)
        key = f"ai_vote|{res['ticker']}|{res['tab']}|{lang}|{res.get('prompt_version')}"
        st.feedback("thumbs", key=key)
        _save_vote(key, res, lang)
        if st.session_state.get(key) is not None:
            st.caption(x["thanks"])


def usage_caption() -> Optional[str]:
    """Running AI total for the sidebar (debug): calls, tokens and estimated cost in this server process."""
    if not enabled():
        return None
    from core.ai_summary.service import TOTALS

    return (f"AI summaries ({settings.ai_model}): {TOTALS['calls']} calls · {TOTALS['tokens']:,} tokens · "
            f"~${TOTALS['cost_usd']:.2f} since start")
