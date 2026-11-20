"""Regression test: HTML blocks rendered through st.markdown must not contain a blank line.
A blank line ends the HTML block in Markdown, and the rest of the HTML is then printed on the page as
raw text (this happened with multi-line tooltips). Run with:  pytest -m network"""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from app.components.ui import attr

pytestmark = pytest.mark.network
APP = str(Path(__file__).resolve().parent.parent / "app" / "streamlit_app.py")


def test_attr_has_no_line_breaks():
    out = attr("What it means: a.\n\nHow it's calculated: b's \"x\".")
    assert "\n" not in out and "&#10;&#10;" in out and "&#x27;" in out and "&quot;" in out


@pytest.mark.parametrize("ticker,lang", [("AAPL", "en"), ("JPM", "id")])
def test_no_blank_lines_inside_html_blocks(ticker, lang):
    at = AppTest.from_file(APP, default_timeout=300)
    at.session_state["ticker"] = ticker
    at.session_state["lang"] = lang
    at.run()
    assert not at.exception
    html_blocks = [m.value for m in at.markdown if "<div" in m.value or "<span" in m.value]
    assert html_blocks, "expected the HTML header / overview blocks"
    for block in html_blocks:
        assert "\n\n" not in block, block[:300]
