"""Sidebar: ticker input + search, recently viewed, language, safe mode, refresh."""
from __future__ import annotations

import streamlit as st

from config.settings import settings
from core import cache
from core.providers import registry
from core.i18n import t
from core.providers.base import ProviderError

MAX_RECENT = 8


def set_ticker(symbol: str) -> None:
    """Callback used by every 'load this ticker' control."""
    st.session_state.ticker = symbol
    st.session_state.ticker_input = symbol


def _on_text_input() -> None:
    value = (st.session_state.get("ticker_input") or "").strip()
    if value:
        st.session_state.ticker = value


def _on_search() -> None:
    choice = st.session_state.get("ticker_search")
    if choice:
        set_ticker(choice)
        st.session_state.ticker_search = None


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


def render_sidebar(current_cik: str | None = None) -> None:
    lang = st.session_state.get("lang", "en")
    with st.sidebar:
        st.title("📈 US Stock Dashboard")
        st.caption("Nanovest internal demo")

        st.text_input(t("sidebar.ticker", lang), key="ticker_input", on_change=_on_text_input,
                      placeholder="e.g. AAPL, JPM, BRK.B",
                      help=t("sidebar.ticker_help", lang))
        options = _search_options()
        if options:
            st.selectbox(t("sidebar.search", lang), options=list(options.keys()), index=None,
                         key="ticker_search", on_change=_on_search, placeholder=t("sidebar.search_placeholder", lang),
                         format_func=lambda tk: f"{tk} — {options.get(tk, '')}")

        if st.session_state.recent:
            st.markdown(f"**{t('sidebar.recent', lang)}**")
            cols = st.columns(4)
            for i, sym in enumerate(st.session_state.recent):
                cols[i % 4].button(sym, key=f"recent_{sym}", on_click=set_ticker, args=(sym,))

        st.divider()
        st.segmented_control(t("sidebar.language", lang), options=["en", "id"], key="lang", required=True,
                             format_func=lambda x: {"en": "English", "id": "Bahasa Indonesia"}[x],
                             help="English / Bahasa Indonesia")
        st.toggle(t("sidebar.safe_mode", lang), key="safe_mode", help=t("sidebar.safe_help", lang))

        if st.button(t("sidebar.refresh", lang), help=t("sidebar.refresh_help", lang)):
            cache.clear_ticker(st.session_state.ticker, extra_tags=(current_cik,) if current_cik else ())
            st.toast(f"Cleared cached data for {st.session_state.ticker}")

        st.divider()
        st.markdown(f"**{t('sidebar.sources', lang)}**")
        st.caption(("✅" if settings.sec_user_agent_ok else "⚠️") + " SEC EDGAR"
                   + ("" if settings.sec_user_agent_ok else " — set your email in SEC_USER_AGENT (.env)"))
        st.caption("✅ yfinance (demo only)")
        st.caption(("✅ Finnhub (demo only)" if settings.finnhub_enabled else "➖ Finnhub off (no API key)"))
        st.caption(f"Price provider: {settings.price_provider}")
        st.markdown("<span class='lb lic'>Licensed-safe</span> <span class='lb calc'>Calculated</span> "
                    "<span class='lb demo'>Demo data</span>", unsafe_allow_html=True)
