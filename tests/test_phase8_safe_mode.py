"""Phase 8 acceptance: in production-safe mode, no orange 'Demo data' item is shown anywhere in the main page.
Renders the whole app (all tabs) with Streamlit's test runner. Run with:  pytest -m network"""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

pytestmark = pytest.mark.network
APP = str(Path(__file__).resolve().parent.parent / "app" / "streamlit_app.py")


def _walk(node):
    if type(node).__name__ == "Tab" and getattr(node, "label", "") in ("Data sources", "Sumber data"):
        return   # the coverage report lists license categories on purpose (values there are hidden)
    proto = getattr(node, "proto", None)
    if proto is not None:
        yield type(node).__name__, str(proto)
    for ch in (getattr(node, "children", {}) or {}).values():
        yield from _walk(ch)


TAB_LABELS = ["Overview", "Price", "Earnings", "Financials", "Valuation", "Health",
              "Dividends", "Ownership", "News", "About"]


def demo_leaks(ticker: str) -> tuple[list, list]:
    """Tabs are lazy (only the selected one runs), so open each tab in turn and scan it."""
    at = AppTest.from_file(APP, default_timeout=300)
    at.session_state["ticker"] = ticker
    at.session_state["ticker_input"] = ticker
    at.session_state["safe_mode"] = True
    leaks, exceptions = [], []
    for label in TAB_LABELS:
        at.session_state["main_tab_en"] = label
        at.run()
        exceptions += [e.value for e in at.exception]
        leaks += [(f"{label} / {k}", s) for k, s in _scan(at)]
    return leaks, exceptions


def _scan(at) -> list:
    leaks = []
    for kind, txt in _walk(at.main):
        # demo-derived content without a badge must not appear either
        for phrase in ("Data check: our ratios vs Yahoo", "Data quality check: SEC vs yfinance",
                       "Z-score (scale capped", "vs the Graham number", "vs price"):
            if phrase in txt:
                leaks.append((kind, phrase))
        if "Demo data" in txt:
            i = txt.find("Demo data")
            leaks.append((kind, txt[max(0, i - 160): i + 40].replace("\\n", " ")))
    return leaks


@pytest.mark.parametrize("ticker", ["AAPL", "JPM", "KO", "TSLA", "PLUG"])
def test_safe_mode_hides_all_demo_items(ticker):
    leaks, exceptions = demo_leaks(ticker)
    assert not exceptions
    assert not leaks, "\n".join(f"{k}: {s}" for k, s in leaks)


if __name__ == "__main__":   # quick manual audit:  python tests/test_phase8_safe_mode.py AAPL JPM
    import sys
    for t in sys.argv[1:] or ["AAPL"]:
        leaks, exc = demo_leaks(t)
        print(f"== {t}: exceptions={exc} leaks={len(leaks)}")
        for k, s in leaks:
            print("  ", k, "|", s)
