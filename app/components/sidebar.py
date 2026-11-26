"""Search bar (top of the page, visible on every device) and the settings sidebar."""
from __future__ import annotations

import streamlit as st

from config.settings import settings
from core import cache
from core.i18n import t
from core.providers import registry
from core.providers.base import ProviderError

MAX_RECENT = 8


def set_ticker(symbol: str) -> None:
    """Callback used by every 'load this ticker' control."""
    st.session_state.ticker = symbol
    st.session_state.ticker_input = symbol


def _on_search() -> None:
    choice = st.session_state.get("ticker_search")
    if choice and str(choice).strip():
        set_ticker(str(choice).strip().upper())
    st.session_state.ticker_search = None


def _on_text_input() -> None:
    value = (st.session_state.get("ticker_input") or "").strip()
    if value:
        st.session_state.ticker = value


def _on_recent() -> None:
    choice = st.session_state.get("recent_pick")
    if choice:
        set_ticker(choice)
    st.session_state.recent_pick = None


def add_recent(symbol: str) -> None:
    recent = [s for s in st.session_state.get("recent", []) if s != symbol]
    st.session_state.recent = [symbol, *recent][:MAX_RECENT]


@st.cache_data(ttl=24 * 3600, show_spinner=False)
def _search_options() -> dict[str, str]:
    try:
        tmap = registry.sec().get_ticker_map()
    except ProviderError:
        return {}
    return {tk.replace("-", "."): row["title"] for tk, row in tmap.items()}


def init_state() -> None:
    st.session_state.setdefault("ticker", "AAPL")
    st.session_state.setdefault("ticker_input", st.session_state.ticker)
    st.session_state.setdefault("recent", [])
    st.session_state.setdefault("lang", settings.language)
    st.session_state.setdefault("safe_mode", settings.production_safe_mode)
    st.session_state.setdefault("show_sources", False)


def render_search() -> None:
    """One search box: pick a company by name or type any ticker and press Enter."""
    lang = st.session_state.get("lang", "en")
    options = _search_options()
    left, right = st.columns([3, 2], vertical_alignment="bottom")
    with left:
        if options:
            st.selectbox(t("search.label", lang), options=list(options.keys()), index=None, key="ticker_search",
                         on_change=_on_search, accept_new_options=True, label_visibility="collapsed",
                         placeholder=t("search.placeholder", lang),
                         format_func=lambda tk: f"{tk}  ·  {options[tk]}" if tk in options else str(tk).upper())
        else:   # SEC list unavailable: plain ticker box
            st.text_input(t("search.label", lang), key="ticker_input", on_change=_on_text_input,
                          label_visibility="collapsed", placeholder=t("search.placeholder_plain", lang))
    with right:
        recent = [s for s in st.session_state.get("recent", []) if s != st.session_state.ticker][:5]
        if recent:
            st.pills(t("search.recent", lang), recent, key="recent_pick", on_change=_on_recent,
                     label_visibility="collapsed")


def render_sidebar(current_cik: str | None = None) -> None:
    lang = st.session_state.get("lang", "en")
    with st.sidebar:
        st.markdown(f"### {t('sidebar.title', lang)}")
        st.caption(t("sidebar.subtitle", lang))

        st.segmented_control(t("sidebar.language", lang), options=["en", "id"], key="lang", required=True,
                             format_func=lambda x: {"en": "English", "id": "Bahasa Indonesia"}[x])
        st.toggle(t("sidebar.show_sources", lang), key="show_sources", help=t("sidebar.show_sources_help", lang))
        st.toggle(t("sidebar.safe_mode", lang), key="safe_mode", help=t("sidebar.safe_help", lang))

        if st.button(t("sidebar.refresh", lang), help=t("sidebar.refresh_help", lang)):
            cache.clear_ticker(st.session_state.ticker, extra_tags=(current_cik,) if current_cik else ())
            st.session_state.force_reload = True
            st.rerun()

        with st.expander(t("sidebar.sources", lang)):
            st.caption(("Connected" if settings.sec_user_agent_ok else "Off: set SEC_USER_AGENT in .env or Secrets")
                       + " · SEC EDGAR (official filings)")
            st.caption("Connected · yfinance (demo only)")
            st.caption(("Connected" if settings.finnhub_enabled else "Off: no API key") + " · Finnhub (demo only)")
            st.caption(f"Price provider: {settings.price_provider}")
            from app.components.ai_card import usage_caption   # running AI cost (debug), SPEC 15.9
            if cap := usage_caption():
                st.caption(cap)
            st.markdown("<span class='lb lic'>Licensed-safe</span> <span class='lb calc'>Calculated</span> "
                        "<span class='lb demo'>Demo data</span>", unsafe_allow_html=True)
