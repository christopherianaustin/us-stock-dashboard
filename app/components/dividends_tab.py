"""Tab 7: Dividends (content hidden when the company pays no dividend)."""
from __future__ import annotations

from typing import Optional

import pandas as pd
import streamlit as st

from app.components import charts, ui
from core.extras_service import DividendData
from core.financials import Financials, period_label
from core.glossary import tooltip
from core.models import DataPoint, LicenseTag, Source


def _demo(note: str) -> DataPoint:
    return DataPoint(value=1, source=Source.YFINANCE, license_tag=LicenseTag.DEMO_ONLY, note=note)


def _calc(note: str) -> DataPoint:
    return DataPoint(value=1, source=Source.CALCULATED, license_tag=LicenseTag.CALCULATED_SAFE, derived=True, note=note)


def _pct(v) -> str:
    return "N/A" if v is None or pd.isna(v) else f"{v * 100:.2f}%"


def render_dividends_tab(d: Optional[DividendData], fin: Optional[Financials]) -> None:
    if d is None:
        st.info("Dividend data is not available right now.")
        return
    s = d.summary
    if not s.pays:
        st.info(f"💡 {s.reason}", icon=None)
        st.caption("Many growth companies reinvest their profits instead of paying dividends. "
                   "Some return cash through share buybacks instead (see Financials → Cash Flow).")
        return
    if ui.safe_mode():
        st.info(f"Dividend per share history and yield: {ui.SAFE_MODE_TEXT}. The payout ratio (from SEC filings) "
                f"is {_pct(d.payout_ratio)}; declared dividends per share are in Financials → Cash Flow.")
        return

    freq = {12: "monthly", 4: "quarterly", 2: "twice a year", 1: "once a year"}.get(s.frequency, "")
    st.markdown(f"##### Dividend overview" + (f" · paid {freq}" if freq else ""),
                help=tooltip("dividend_yield", ui.lang()))
    c = st.columns(6)
    c[0].metric("Yield (TTM)", _pct(s.yield_ttm), help=tooltip("dividend_yield", ui.lang()))
    c[0].caption(f"${s.dps_ttm:,.2f} per share in 12 months" + (f" · 5y avg {_pct(s.yield_5y_avg)}" if s.yield_5y_avg else ""))
    c[1].metric("Payout ratio", _pct(d.payout_ratio), help=tooltip("payout_ratio", ui.lang()))
    c[1].caption("of net income (SEC)")
    c[2].metric("FCF payout", _pct(d.fcf_payout), help=tooltip("fcf_payout", ui.lang()))
    c[2].caption("of free cash flow (SEC)" if d.fcf_payout is not None else
                 ("not meaningful for banks" if fin is not None and fin.is_financial else "needs positive FCF"))
    c[3].metric("Dividend growth 5y (CAGR)", _pct(s.cagr_5y), help=tooltip("dividend_growth", ui.lang()))
    c[3].caption(f"3y: {_pct(s.cagr_3y)}")
    c[4].metric("Growth streak", f"{s.streak} years", help=tooltip("dividend_growth", ui.lang()))
    c[4].caption("dividend aristocrat level (25+ years)" if s.streak >= 25 else "consecutive yearly raises")
    c[5].metric("Next ex-dividend date", f"{d.next_ex_date:%d %b %Y}" if d.next_ex_date else "N/A",
                help=tooltip("ex_dividend", ui.lang()))
    c[5].caption("not announced yet" if not d.next_ex_date else
                 f"last: ${s.last_amount:,.4g} on {s.last_ex_date:%d %b %Y}")
    ui.badge(_demo("Dividend history and ex-dates (Yahoo Finance); payout ratios calculated from SEC filings"))
    st.divider()

    st.markdown("##### Dividends per share by year", help=tooltip("dividend_growth", ui.lang()))
    a = d.annual.tail(15)
    if not a.empty:
        x = [str(y) for y in a.index]
        st.plotly_chart(charts.bars(x, [("Dividend per share", list(a.values))], kind="eps"),
                        key=f"{d.symbol}_dps_bars", config={"displayModeBar": False})
        st.caption("Complete calendar years, by ex-dividend date. Special one-off dividends are included in the "
                   "yearly total.")
        ui.badge(_demo("Dividend history (Yahoo Finance)"))
        with st.expander("Full dividend history"):
            hist = d.dividends.sort_index(ascending=False).rename("dividend per share").to_frame()
            hist.index = hist.index.date
            st.dataframe(hist, width="stretch")
            st.download_button("Download CSV", d.dividends.to_csv().encode("utf-8"),
                               file_name=f"{d.symbol}_dividends.csv", mime="text/csv", key=f"dl_div_{d.symbol}")
            if not d.sec_dps.empty:
                st.caption("Cross-check, dividends declared per share in SEC annual reports (by fiscal year): "
                           + ", ".join(f"FY{y}: ${v:,.2f}" for y, v in d.sec_dps.tail(5).items()))

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("##### Dividend yield over 5 years", help=tooltip("dividend_yield", ui.lang()))
        y = d.yield_hist.dropna()
        y = y[y.index > y.index.max() - pd.DateOffset(years=5)] if len(y) else y
        if len(y):
            st.plotly_chart(charts.line_with_reference(y.index, y, "Yield (TTM)", s.yield_5y_avg, "5y average"),
                            key=f"{d.symbol}_yield_hist", config={"displayModeBar": False})
            st.caption("Above the average line: the stock yields more than usual (price lower or dividend higher).")
            ui.badge(_demo("Dividends and prices from demo sources"))
        else:
            st.caption("N/A (price history unavailable)")
    with c2:
        st.markdown("##### Payout ratio over time (TTM)", help=tooltip("payout_ratio", ui.lang()))
        ph = d.payout_hist
        if len(ph) and fin is not None:
            meta = fin.tidy[fin.tidy["period_type"] == "Q"].drop_duplicates("period_end").set_index("period_end")
            x = [period_label(meta.loc[pe, "fiscal_year"], meta.loc[pe, "fiscal_quarter"], "Q") if pe in meta.index
                 else f"{pe:%b %Y}" for pe in ph.index]
            st.plotly_chart(charts.lines(x, [("Payout ratio", list(ph.values))], kind="pct", height=300),
                            key=f"{d.symbol}_payout_hist", config={"displayModeBar": False})
            ui.badge(_calc("Dividends paid / net income from SEC filings"))
        else:
            st.caption("N/A (needs dividends paid and net income from SEC filings)")
