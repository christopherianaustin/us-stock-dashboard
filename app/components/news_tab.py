"""Tab 9: News & Filings."""
from __future__ import annotations

import html
from typing import Optional

import pandas as pd
import streamlit as st

from app.components import ui
from core.extras_service import NewsData
from core.glossary import tooltip
from core.models import DataPoint, LicenseTag, Source

FORM_GROUPS = {"Earnings & events (8-K)": {"8-K", "8-K/A"}, "Quarterly (10-Q)": {"10-Q", "10-Q/A"},
               "Annual (10-K)": {"10-K", "10-K/A", "20-F"}, "Insider trades (Form 4)": {"4"},
               "Other": {"DEF 14A", "S-1", "SC 13G", "SC 13D", "SC 13G/A", "SC 13D/A", "6-K"}}


def _news(n: NewsData) -> None:
    st.markdown("#### News", help=tooltip("news", ui.lang()))
    if ui.safe_mode():
        st.info(f"News: {ui.SAFE_MODE_TEXT}.")
        return
    days = st.segmented_control("Show", ["Last 7 days", "Last 30 days"], default="Last 7 days", required=True,
                                key=f"news_days_{n.symbol}")
    cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=7 if days == "Last 7 days" else 30)
    items = [i for i in n.items if (i["datetime"] if i["datetime"].tzinfo else i["datetime"].tz_localize("UTC")) >= cutoff]
    if not items:
        st.caption("No news in this period.")
        return
    for it in items[:30]:
        c1, c2 = st.columns([1, 6], vertical_alignment="top")
        with c1:
            if it.get("image"):
                st.image(it["image"], width=110)
        with c2:
            ts = it["datetime"].tz_convert("America/New_York") if it["datetime"].tzinfo else it["datetime"]
            st.markdown(f"**[{html.escape(it['headline'])}]({it['url']})**")
            summary = (it.get("summary") or "").strip()
            if len(summary) > 220:
                summary = summary[:220].rsplit(" ", 1)[0] + "…"
            st.caption(f"{ts:%d %b %Y, %H:%M} ET · {it['source']}" + (f" — {summary}" if summary else ""))
    st.caption(f"Showing {min(len(items), 30)} of {len(items)} articles. Headlines are not verified by us; "
               "links open the original source.")
    ui.badge(DataPoint(value=1, source=Source.FINNHUB if n.source == Source.FINNHUB.value else Source.YFINANCE,
                       license_tag=LicenseTag.DEMO_ONLY, note="Company news (demo data)"))


def _filings(n: NewsData) -> None:
    st.markdown("#### SEC filings", help=tooltip("sec_filings", ui.lang()))
    if n.filings_note:
        st.caption(n.filings_note)
    if not n.filings:
        return
    groups = st.segmented_control("Filing types", list(FORM_GROUPS), selection_mode="multi",
                                  default=list(FORM_GROUPS)[:4], key=f"filing_types_{n.symbol}")
    wanted = set().union(*(FORM_GROUPS[g] for g in (groups or []))) if groups else set()
    rows = []
    for f in n.filings:
        if f.form not in wanted:
            continue
        what = f.description or ""
        if f.form.startswith("8-K") and f.items:
            what = ("Earnings results" if "2.02" in f.items else what) + f" (items {f.items})"
        if f.form == "4":
            what = "Insider transaction report"
        rows.append({"form": f.form, "filed": f.filing_date, "period": f.report_date, "description": what,
                     "link": f.url or f.index_url})
        if len(rows) >= 40:
            break
    if not rows:
        st.caption("No filings of the selected types in the recent list.")
        return
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch",
                 column_config={"link": st.column_config.LinkColumn(display_text="open ↗")})
    st.caption("10-K = annual report · 10-Q = quarterly report · 8-K = important event (item 2.02 = earnings) · "
               "Form 4 = insider trade.")
    ui.badge(DataPoint(value=1, source=Source.SEC, license_tag=LicenseTag.COMMERCIAL_OK, note="SEC EDGAR filing index"))


def render_news_tab(n: Optional[NewsData]) -> None:
    if n is None:
        st.info("News and filings are not available right now.")
        return
    _news(n)
    st.divider()
    _filings(n)
