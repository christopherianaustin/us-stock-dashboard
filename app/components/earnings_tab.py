"""Tab 3: Earnings - actual vs expected, beat rate, price reaction, GAAP vs adjusted, revisions, upcoming."""
from __future__ import annotations

from typing import Optional

import pandas as pd
import streamlit as st

from app.components import charts, ui
from core.earnings import revision_direction
from core.earnings_service import EarningsData
from core.glossary import tooltip
from core.models import DataPoint, LicenseTag, Source


def _demo(note: str) -> DataPoint:
    return DataPoint(value=1, source=Source.YFINANCE, license_tag=LicenseTag.DEMO_ONLY, note=note)


def _sec(note: str) -> DataPoint:
    return DataPoint(value=1, source=Source.SEC, license_tag=LicenseTag.COMMERCIAL_OK, note=note)


def _x(h: pd.DataFrame) -> list[str]:
    return [f"{q}<br><span style='font-size:10px'>{d:%d %b %y}</span>" for q, d in zip(h["quarter"], h["date"])]


def _f(v) -> Optional[float]:
    return None if v is None or pd.isna(v) else float(v)


def _upcoming(e: EarningsData) -> None:
    u = e.upcoming
    st.markdown("##### Next earnings report", help=tooltip("upcoming_earnings", ui.lang()))
    c = st.columns(5)
    if u.get("date") is not None:
        c[0].metric("Date", f"{u['date']:%d %b %Y}", delta=f"in {u['days']} days", delta_color="off")
        c[0].caption(f"Expected {u.get('timing', 'time unknown')} (not confirmed until the company announces it)")
    else:
        c[0].metric("Date", "N/A")
        c[0].caption("Next earnings date not announced yet")
    c[1].metric("Expected EPS", ui.fmt_money(u.get("eps_estimate")))
    if u.get("eps_low") is not None:
        c[1].caption(f"Range {ui.fmt_money(u.get('eps_low'))} – {ui.fmt_money(u.get('eps_high'))}")
    c[2].metric("EPS a year ago", ui.fmt_money(u.get("year_ago_eps")))
    if u.get("eps_estimate") and u.get("year_ago_eps"):
        c[2].caption(f"Expected growth {u['eps_estimate'] / u['year_ago_eps'] - 1:+.1%}")
    c[3].metric("Expected revenue", ui.fmt_big_money(u.get("revenue_estimate")))
    c[4].metric("Analysts", f"{int(u['analysts'])}" if u.get("analysts") else "N/A")
    ui.badge(_demo("Earnings calendar and analyst estimates (Yahoo Finance)"))


def _stats(e: EarningsData) -> None:
    c = st.columns(4)
    for col, (label, br) in zip(c[:2], (("Beat rate (last 8 quarters)", e.beat_rate_8),
                                        ("Beat rate (last 12 quarters)", e.beat_rate_12))):
        rate, beats, n = br
        col.metric(label, f"{rate:.0%}" if rate is not None else "N/A", help=tooltip("beat_rate", ui.lang()))
        if n:
            col.caption(f"Beat estimates in {beats} of the last {n} quarters")
    c[2].metric("Typical earnings move", f"±{e.typical_move:.1%}" if e.typical_move is not None else "N/A",
                help=tooltip("earnings_reaction", ui.lang()))
    c[2].caption("Average size of the 1-day move after earnings")
    last = e.history.iloc[-1] if not e.history.empty else None
    if last is not None:
        c[3].metric("Latest surprise", f"{last['surprise_pct']:+.1f}%" if pd.notna(last["surprise_pct"]) else "N/A",
                    help=tooltip("eps_surprise", ui.lang()))
        c[3].caption(f"{last['quarter']}: {last['result'] or 'n/a'}")
    ui.badge(_demo("EPS estimates and reported EPS (Yahoo Finance); price moves from demo prices"))


def _charts(e: EarningsData) -> None:
    h = e.history
    x = _x(h)
    st.markdown("##### EPS: actual vs expected (green = beat, red = miss, gray = within ±1%)",
                help=tooltip("eps_surprise", ui.lang()))
    st.plotly_chart(charts.eps_vs_estimate(x, list(h["eps_estimate"]), list(h["eps_reported"]), list(h["result"]),
                                           list(h["surprise_pct"])), key=f"{e.symbol}_eps_vs_est",
                    config={"displayModeBar": False})
    st.caption("“Reported EPS (usually adjusted)”: the number analysts compare against, from Yahoo Finance.")
    ui.badge(_demo("EPS estimates and reported EPS"))

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("##### Price move 1 day after each report", help=tooltip("earnings_reaction", ui.lang()))
        if h["move_1d"].notna().any():
            st.plotly_chart(charts.signed_bars(x, list(h["move_1d"]), "1-day move"), key=f"{e.symbol}_reaction",
                            config={"displayModeBar": False})
        else:
            st.caption("N/A (price history unavailable)")
        ui.badge(_demo("Calculated from demo daily prices"))
    with c2:
        st.markdown("##### GAAP EPS (SEC) vs reported EPS (usually adjusted)", help=tooltip("gaap_vs_adjusted", ui.lang()))
        series = [("GAAP diluted EPS (SEC)", [_f(v) for v in h["eps_gaap"]]),
                  ("Reported EPS", [_f(v) for v in h["eps_reported"]])]
        if any(v is not None for v in series[0][1]):
            st.plotly_chart(charts.lines(x, series, kind="eps", height=320), key=f"{e.symbol}_gaap",
                            config={"displayModeBar": False})
            st.caption("A lasting gap means the adjusted number excludes items (e.g. one-off gains or charges).")
        else:
            st.caption("GAAP EPS: N/A (not reported in a standard form by this company)")
        ui.badge(_sec("GAAP EPS from 10-Q / 10-K filings (reported EPS: demo data)"))

    st.markdown("##### Revenue: actual vs expected", help=tooltip("revenue_surprise", ui.lang()))
    if h["revenue"].notna().any():
        st.plotly_chart(charts.revenue_vs_estimate(x, list(h["revenue"]), list(h["revenue_estimate"])),
                        key=f"{e.symbol}_rev_vs_est", config={"displayModeBar": False})
        n_est = int(h["revenue_estimate"].notna().sum())
        st.caption("Gray marks = analyst revenue estimate. " + (
            f"Estimates available for {n_est} quarter(s) only: past revenue estimates need a paid data provider."
            if n_est < len(h) else ""))
        ui.badge(_sec("Actual revenue from SEC filings (estimates: Finnhub demo data)"))
    else:
        st.caption("N/A (no revenue data)")


def _revisions(e: EarningsData) -> None:
    st.markdown("##### How analysts' EPS estimates changed (last 90 days)", help=tooltip("estimate_revisions", ui.lang()))
    r = e.revisions
    if r.empty:
        st.caption("N/A (no estimate history available)")
        return
    cols = st.columns(2)
    for col, period in zip(cols, ("Current quarter", "Next fiscal year")):
        with col:
            if period not in r.index:
                st.caption(f"{period}: N/A")
                continue
            row = r.loc[period]
            direction = revision_direction(row)
            word = {"up": "raised ↑", "down": "lowered ↓", "flat": "about unchanged"}.get(direction, "")
            st.caption(f"{period} EPS estimate" + (f": analysts {word}" if word else ""))
            fig = charts.lines(list(row.index), [(f"{period} estimate", [_f(v) for v in row.values])], kind="eps",
                               height=240)
            st.plotly_chart(fig, key=f"{e.symbol}_rev_{period}", config={"displayModeBar": False})
    if not e.revision_counts.empty:
        st.caption("Number of analysts who raised (up) or lowered (down) their EPS estimate:")
        st.dataframe(e.revision_counts, width="stretch")
    ui.badge(_demo("Analyst estimate trend and revisions (Yahoo Finance)"))


def _table(e: EarningsData) -> None:
    st.markdown("##### Past earnings reports", help=tooltip("eps_surprise", ui.lang()))
    h = e.history.iloc[::-1]
    df = pd.DataFrame({
        "Quarter": h["quarter"],
        "Period end": [f"{d:%Y-%m-%d}" if pd.notna(d) else "—" for d in h["period_end"]],
        "Report date": [f"{d:%Y-%m-%d} ({t})" for d, t in zip(h["date"], h["timing"])],
        "EPS expected": h["eps_estimate"].map(lambda v: "N/A" if v is None or pd.isna(v) else f"${v:,.3f}"),
        "EPS reported (usually adjusted)": h["eps_reported"].map(lambda v: ui.fmt_money(v)),
        "EPS GAAP (SEC)": h["eps_gaap"].map(lambda v: ui.fmt_money(v)),
        "Surprise": h["surprise_pct"].map(lambda v: "N/A" if pd.isna(v) else f"{v:+.1f}%"),
        "Result": h["result"].map(lambda r: {"beat": "🟢 beat", "miss": "🔴 miss", "inline": "⚪ inline"}.get(r, "—")),
        "Revenue (SEC)": h["revenue"].map(lambda v: ui.fmt_big_money(v)),
        "1-day move": h["move_1d"].map(lambda v: "N/A" if v is None or pd.isna(v) else f"{v:+.1%}"),
        "5-day move": h["move_5d"].map(lambda v: "N/A" if v is None or pd.isna(v) else f"{v:+.1%}"),
        "10-Q / 10-K": h["filing_url"],
        "Press release (8-K)": h["press_release_url"],
    })
    st.dataframe(df, hide_index=True, width="stretch", column_config={
        "10-Q / 10-K": st.column_config.LinkColumn(display_text="open filing ↗"),
        "Press release (8-K)": st.column_config.LinkColumn(display_text="open 8-K ↗"),
    })
    st.caption("Links open the official SEC filings. The earnings press release is usually Exhibit 99.1 of the 8-K. "
               "For companies with very many filings, older links open the company's filing list on EDGAR.")
    raw = e.history.drop(columns=["datetime"], errors="ignore")
    st.download_button("Download CSV", raw.to_csv(index=False).encode("utf-8"), file_name=f"{e.symbol}_earnings.csv",
                       mime="text/csv", key=f"dl_earn_{e.symbol}")


def _check(e: EarningsData) -> None:
    if e.finnhub_check.empty:
        return
    with st.expander("Data check: EPS estimates from yfinance vs Finnhub"):
        st.caption("Different providers survey different analysts, so estimates differ slightly. Finnhub labels "
                   "quarters by calendar dates, so non-calendar fiscal years look shifted.")
        st.dataframe(e.finnhub_check, hide_index=True, width="stretch")


def render_earnings_tab(e: Optional[EarningsData]) -> None:
    if e is None:
        st.info("Earnings data is not available for this company right now.")
        return
    if ui.safe_mode():
        st.info(f"{ui.SAFE_MODE_TEXT}. Earnings estimates, surprises and the earnings calendar come from demo sources. "
                "Licensed-safe parts (GAAP EPS and revenue from SEC filings) are on the Financials tab.")
        return
    for w in e.warnings:
        st.warning(w, icon="⚠️")
    _upcoming(e)
    st.divider()
    if e.history.empty:
        st.caption("No past earnings data.")
        return
    _stats(e)
    _charts(e)
    st.divider()
    _revisions(e)
    st.divider()
    _table(e)
    _check(e)
