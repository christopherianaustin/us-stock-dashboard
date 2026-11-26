"""AI Insight card at the top of each tab (SPEC 15.7, step 10c).

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

SIGNAL = {  # AI signal -> (pill css class from ui.inject_css, English, Indonesian)
    "Strong": ("strong", "Strong", "Kuat"), "Neutral": ("neutral", "Neutral", "Netral"),
    "Weak": ("weak", "Weak", "Lemah"), "Not enough data": ("na", "Not enough data", "Data belum cukup"),
    "Not applicable": ("na", "Not applicable", "Tidak berlaku"),
}
TXT = {
    "en": {"label": "AI Insight", "auto": "Automatic summary", "pos": "Positives", "watch": "Watch-outs",
           "next": "What to watch next", "ask": "Ask yourself", "gaps": "Data gaps", "writing": "Writing the AI Insight…",
           "footer": "AI-generated from the data on this page (as of {date}). It can make mistakes and is not "
                     "investment advice.",
           "auto_footer": "Automatic summary from our rule-based checks (as of {date}). Not investment advice.",
           "thanks": "Thanks for the feedback."},
    "id": {"label": "Insight AI", "auto": "Ringkasan otomatis", "pos": "Hal positif", "watch": "Perlu diperhatikan",
           "next": "Yang perlu dipantau", "ask": "Tanyakan pada diri sendiri", "gaps": "Data yang kurang",
           "writing": "Sedang menulis Insight AI…",
           "footer": "Dibuat oleh AI dari data di halaman ini (per {date}). Bisa keliru dan bukan saran investasi.",
           "auto_footer": "Ringkasan otomatis dari pemeriksaan berbasis aturan kami (per {date}). Bukan saran investasi.",
           "thanks": "Terima kasih atas masukannya."},
}

CSS = """<style>
.ai-top {display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:6px}
.ai-label {font-size:0.8125rem;font-weight:600;color:#6E3FD1;letter-spacing:.01em}
.ai-head {font-size:1.125rem;line-height:1.5rem;font-weight:600;color:#1D1D1F;margin:2px 0 4px}
.ai-take {font-size:0.9375rem;line-height:1.4rem;color:#424245;margin:0 0 10px;text-wrap:pretty}
.ai-pts {list-style:none;padding:0;margin:0 0 6px}
.ai-pts li {display:flex;gap:8px;font-size:0.9375rem;line-height:1.375rem;color:#1D1D1F;margin:4px 0}
.ai-dot {width:8px;height:8px;border-radius:50%;flex:none;margin-top:7px}
.ai-dot.good {background:#21a35b}.ai-dot.watch {background:#f0a000}
.ai-sub {font-size:0.8125rem;font-weight:600;color:#6E6E73;margin:10px 0 2px}
.ai-small {font-size:0.875rem;line-height:1.3rem;color:#424245;margin:2px 0}
.ai-foot {font-size:0.75rem;line-height:1.1rem;color:#86868B;margin-top:10px}
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


def _pts(items: list, cls: str) -> str:
    rows = "".join(f"<li><span class='ai-dot {cls}'></span><span>{html.escape(p['text'] if isinstance(p, dict) else p)}"
                   "</span></li>" for p in items)
    return f"<ul class='ai-pts'>{rows}</ul>" if rows else ""


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
    if res["source"] == "fallback" and not (s["positives"] or s["watch_outs"]):
        ph.empty()            # nothing to show: hide rather than show an empty box
        return
    css, en, idn = SIGNAL.get(s["signal"], SIGNAL["Not enough data"])
    chip = f"<span class='pill {css}'>{html.escape(idn if lang == 'id' else en)}</span>"
    with ph.container(border=True):
        if res["source"] == "ai":
            body = (f"<div class='ai-top'><span class='ai-label'>✨ {x['label']}</span>{chip}</div>"
                    f"<div class='ai-head'>{html.escape(s['headline'])}</div>"
                    f"<p class='ai-take'>{html.escape(s['takeaway'])}</p>"
                    + _pts(s["positives"], "good") + _pts(s["watch_outs"], "watch"))
            if s["what_to_watch_next"]:
                body += f"<div class='ai-sub'>{x['next']}</div>" + "".join(
                    f"<p class='ai-small'>📅 {html.escape(w)}</p>" for w in s["what_to_watch_next"])
            body += f"<div class='ai-sub'>{x['ask']}</div><p class='ai-small'>{html.escape(s['ask_yourself'])}</p>"
            body += f"<div class='ai-foot'>{html.escape(x['footer'].format(date=_date(res.get('as_of'))))}</div>"
        else:
            body = (f"<div class='ai-top'><span class='ai-label'>{x['auto']}</span>{chip}</div>"
                    + _pts(s["positives"], "good") + _pts(s["watch_outs"], "watch")
                    + f"<div class='ai-foot'>{html.escape(x['auto_footer'].format(date=_date(res.get('as_of'))))}</div>")
        st.markdown(CSS + body, unsafe_allow_html=True)
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
