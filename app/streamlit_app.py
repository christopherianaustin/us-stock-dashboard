"""Main Streamlit page. Run with:  streamlit run app/streamlit_app.py"""
from __future__ import annotations

import sys
from pathlib import Path

# Make the project root importable (so `core`, `config`, `app` work when run via streamlit)
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402

from app.components import ui  # noqa: E402
from app.components.dividends_tab import render_dividends_tab  # noqa: E402
from app.components.earnings_tab import render_earnings_tab  # noqa: E402
from app.components.financials_tab import render_financials_tab  # noqa: E402
from app.components.header import render_header  # noqa: E402
from app.components.health_tab import render_health_tab  # noqa: E402
from app.components.news_tab import render_news_tab  # noqa: E402
from app.components.ownership_tab import render_ownership_tab  # noqa: E402
from app.components.price_tab import render_price_tab  # noqa: E402
from app.components.profile_tab import render_profile_tab  # noqa: E402
from app.components.sidebar import add_recent, init_state, render_sidebar, set_ticker  # noqa: E402
from app.components.summary_tab import render_summary_tab  # noqa: E402
from app.components.valuation_tab import render_valuation_tab  # noqa: E402
from core.bundle import load_bundle  # noqa: E402
from core.company import TickerNotFound, resolve_ticker  # noqa: E402
from core.i18n import t  # noqa: E402
from core.logging_setup import get_logger  # noqa: E402

log = get_logger("app")

TAB_KEYS = ["summary", "price", "earnings", "financials", "valuation", "health", "dividends", "ownership", "news",
            "profile"]
PART_NAMES = {"financials": "Financial statements", "ratios": "Ratios", "prices": "Prices and technicals",
              "earnings": "Earnings", "dividends": "Dividends", "ownership": "Ownership", "news": "News and filings"}

st.set_page_config(page_title="US Stock Dashboard", page_icon="📈", layout="wide")
ui.inject_css()
init_state()


def main() -> None:
    lang = ui.lang()
    raw = st.session_state.ticker
    try:
        with st.spinner(t("loading.lookup", lang, symbol=raw)):
            resolved = resolve_ticker(raw)
    except TickerNotFound as exc:
        render_sidebar()
        st.error(f"🔎 {exc}")
        st.info("Try one of these:")
        cols = st.columns(6)
        for i, sym in enumerate(["AAPL", "MSFT", "NVDA", "JPM", "KO", "BRK.B"]):
            cols[i].button(sym, key=f"try_{sym}", on_click=set_ticker, args=(sym,))
        return

    add_recent(resolved.symbol)
    render_sidebar(resolved.cik)
    with st.spinner(t("loading.data", lang, symbol=resolved.symbol)):
        b = load_bundle(resolved)
    sc = b.scorecard(lang=lang, safe_mode=ui.safe_mode())

    render_header(b.header, sc)
    for part, err in b.errors.items():
        st.warning(f"{PART_NAMES.get(part, part)} could not be loaded ({err.split(':')[0]}). Other sections still work.",
                   icon="⚠️")

    tabs = st.tabs([t(f"tabs.{k}", lang) for k in TAB_KEYS])
    renderers = {
        "summary": lambda: render_summary_tab(sc, b.analysis, b.price, b.dividends, b.ownership),
        "price": lambda: render_price_tab(b.price),
        "earnings": lambda: render_earnings_tab(b.earnings),
        "financials": lambda: render_financials_tab(b.fin),
        "valuation": lambda: render_valuation_tab(b.analysis),
        "health": lambda: render_health_tab(b.analysis, b.fin),
        "dividends": lambda: render_dividends_tab(b.dividends, b.fin),
        "ownership": lambda: render_ownership_tab(b.ownership),
        "news": lambda: render_news_tab(b.news),
        "profile": lambda: render_profile_tab(b.header, on_pick_ticker=set_ticker),
    }
    for tab, key in zip(tabs, TAB_KEYS):
        with tab:
            try:
                renderers[key]()
            except Exception as exc:  # noqa: BLE001 - one tab failing must not break the others
                log.exception("Tab %s failed for %s", key, resolved.symbol)
                st.error("This section could not be displayed. Other tabs still work.")
                with st.expander("Technical details"):
                    st.code(f"{type(exc).__name__}: {exc}")


try:
    main()
except Exception as exc:  # noqa: BLE001 - last-resort safety net: never show a raw crash
    log.exception("Unexpected error")
    st.error("Something went wrong while loading this page. Please try again or press 'Refresh data'.")
    with st.expander("Technical details"):
        st.code(f"{type(exc).__name__}: {exc}")
finally:
    ui.disclaimer()
