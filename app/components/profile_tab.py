"""Tab 10: Company Profile."""
from __future__ import annotations

import html
import re

import pandas as pd
import streamlit as st

from app.components import ui
from core.glossary import tooltip
from core.models import DataPoint, HeaderData


def _short(text: str, sentences: int = 2) -> str:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return " ".join(parts[:sentences])


def render_profile_tab(h: HeaderData, on_pick_ticker) -> None:
    p = h.profile

    # ----- business description -----
    st.subheader("What the company does")
    d = p.description
    if ui.hidden_by_safe_mode(d):
        st.info(ui.SAFE_MODE_TEXT)
    elif d.available:
        short = _short(d.value)
        st.write(short)
        if len(short) < len(d.value):
            with st.expander("Read more"):
                st.write(d.value)
        ui.badge(d)
    else:
        st.caption(f"N/A ({d.na_reason})")

    # ----- facts table -----
    st.subheader("Company facts")
    sic = p.sic_code
    if sic.available and p.sic_description.available:
        sic = sic.model_copy(update={"value": f"{sic.value} – {p.sic_description.value}"})
    employees = p.employees
    rows: list[tuple[str, str | None, DataPoint, callable]] = [
        ("Sector", None, p.sector, str),
        ("Industry", None, p.industry, str),
        ("SIC industry code", "sic_code", sic, str),
        ("Employees", "employees", employees, ui.fmt_int),
        ("Headquarters", None, p.headquarters, str),
        ("Website", None, p.website, str),
        ("CEO", None, p.ceo, str),
        ("Fiscal year end", "fiscal_year_end", p.fiscal_year_end, str),
        ("IPO date", "ipo_date", p.ipo_date, str),
        ("State of incorporation", None, p.state_of_incorporation, str),
        ("Shares outstanding", "shares_outstanding", h.shares_outstanding, ui.fmt_int),
    ]
    html_rows = []
    csv_rows = []
    for label, gkey, dp, fmt in rows:
        tip = tooltip(gkey, ui.lang()) if gkey else ""
        label_html = html.escape(label) + (f" <span title='{ui.attr(tip)}' style='cursor:help'>ⓘ</span>" if tip else "")
        value_html = ui.text_value(dp, fmt)
        if label == "Website" and dp.available and not ui.hidden_by_safe_mode(dp):
            url = dp.value if str(dp.value).startswith("http") else f"https://{dp.value}"
            value_html = f"<a href='{html.escape(url)}' target='_blank'>{html.escape(str(dp.value))}</a>"
        badge = "" if ui.hidden_by_safe_mode(dp) else ui.badge_html(dp)
        html_rows.append(f"<tr><td class='k'>{label_html}</td><td>{value_html}</td><td class='s'>{badge}</td></tr>")
        csv_rows.append({
            "field": label,
            "value": (ui.SAFE_MODE_TEXT if ui.hidden_by_safe_mode(dp) else (fmt(dp.value) if dp.available else "N/A")),
            "na_reason": dp.na_reason if not dp.available else "",
            "source": dp.source.value if dp.source else "",
            "license_tag": dp.license_tag.value if dp.license_tag else "",
        })
    st.html(f"<table class='ptable'>{''.join(html_rows)}</table>")

    c1, c2 = st.columns(2)
    with c1:
        st.download_button("Download CSV", pd.DataFrame(csv_rows).to_csv(index=False).encode("utf-8"),
                           file_name=f"{h.symbol}_profile.csv", mime="text/csv")
    with c2:
        if p.sec_filings_url:
            st.link_button("All SEC filings ↗", p.sec_filings_url)

    # ----- peers -----
    st.subheader("Similar companies (peers)")
    peers = p.peers
    if ui.hidden_by_safe_mode(peers):
        st.info(ui.SAFE_MODE_TEXT)
    elif peers.available:
        st.caption("Click a ticker to load it.")
        cols = st.columns(min(len(peers.value), 8))
        for i, sym in enumerate(peers.value):
            cols[i % len(cols)].button(sym, key=f"peer_{sym}", on_click=on_pick_ticker, args=(sym,))
        ui.badge(peers)
    else:
        st.caption(f"N/A ({peers.na_reason})")
