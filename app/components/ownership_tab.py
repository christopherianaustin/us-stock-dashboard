"""Tab 8: Ownership & Sentiment. Analyst ratings are third-party opinions and always labeled as such."""
from __future__ import annotations

from typing import Optional

import pandas as pd
import streamlit as st

from app.components import charts, ui
from core.extras_service import OwnershipData
from core.glossary import tooltip
from core.models import DataPoint, LicenseTag, Source
from core.sentiment import RATING_COLS, RATING_LABELS


def _demo(src: str, note: str) -> DataPoint:
    s = Source.FINNHUB if src == Source.FINNHUB.value else Source.YFINANCE
    return DataPoint(value=1, source=s, license_tag=LicenseTag.DEMO_ONLY, note=note)


def _holders(o: OwnershipData) -> None:
    c1, c2 = st.columns([1, 1.6])
    with c1:
        st.markdown("##### Who owns the shares", help=tooltip("holders", ui.lang()))
        b = o.breakdown
        if b:
            st.plotly_chart(charts.donut(list(b), list(b.values())), key=f"{o.symbol}_holders_donut",
                            config={"displayModeBar": False})
            st.caption(f"Insiders {b['Insiders']:.1%} · institutions {b['Institutions']:.1%}"
                       + (f" ({o.institutions_count:,} institutions)" if o.institutions_count else ""))
        else:
            st.caption("N/A (no ownership breakdown available)")
    with c2:
        st.markdown("##### Top 10 institutional holders", help=tooltip("holders", ui.lang()))
        t = o.top_institutions
        if t.empty:
            st.caption("N/A (no institutional holder data)")
        else:
            show = t.copy()
            if "% of shares" in show:
                show["% of shares"] = show["% of shares"].map(lambda v: f"{v:.2%}")
            if "change in shares" in show:
                show["change in shares"] = show["change in shares"].map(lambda v: f"{v:+.2%}")
            if "value" in show:
                show["value"] = show["value"].map(ui.fmt_big_money)
            if "shares" in show:
                show["shares"] = show["shares"].map(lambda v: f"{v / 1e6:,.1f}M")
            if "date reported" in show:
                show["date reported"] = pd.to_datetime(show["date reported"]).dt.date
            st.dataframe(show, hide_index=True, width="stretch")
            st.download_button("Download CSV", t.to_csv(index=False).encode("utf-8"),
                               file_name=f"{o.symbol}_institutions.csv", mime="text/csv", key=f"dl_inst_{o.symbol}")
    ui.badge(_demo("yfinance", "Holder data from 13F filings, collected by Yahoo Finance"))


def _insiders(o: OwnershipData) -> None:
    st.markdown("##### Insider buying and selling (by month)", help=tooltip("insiders", ui.lang()))
    m = o.insider_monthly
    if m.empty:
        st.caption("No insider purchases or sales reported recently.")
    else:
        x = [f"{d:%b %Y}" for d in m.index]
        st.plotly_chart(charts.signed_bars(x, list(m["net"]), "Net insider buying ($)", kind="money"),
                        key=f"{o.symbol}_insider_net", config={"displayModeBar": False})
        st.caption(f"Green = insiders bought more than they sold; red = sold more. Last 24 months: bought "
                   f"{ui.fmt_big_money(m['bought'].sum())}, sold {ui.fmt_big_money(-m['sold'].sum())}.")
    t = o.insiders
    if not t.empty:
        with st.expander(f"Insider transactions ({len(t)})"):
            show = t.copy()
            show["date"] = show["date"].dt.date
            show["type"] = show["type"].map({"buy": "🟢 purchase", "sell": "🔴 sale", "other": "⚪ other"})
            show["value"] = show["value"].map(lambda v: ui.fmt_big_money(v) if pd.notna(v) and v else "—")
            st.dataframe(show, hide_index=True, width="stretch")
            st.caption("'Other' = stock awards, gifts or option exercises (not counted as buying or selling).")
            st.download_button("Download CSV", t.to_csv(index=False).encode("utf-8"),
                               file_name=f"{o.symbol}_insiders.csv", mime="text/csv", key=f"dl_ins_{o.symbol}")
    ui.badge(_demo("yfinance", "Insider transactions (SEC Form 4) collected by Yahoo Finance"))


def _analysts(o: OwnershipData) -> None:
    st.markdown("#### Wall Street analysts' ratings", help=tooltip("analyst_ratings", ui.lang()))
    st.caption("Third-party opinions from Wall Street analysts. This is **not** our view or a recommendation.")
    rec = o.recommendations
    c1, c2 = st.columns([1.6, 1])
    with c1:
        if rec.empty:
            st.caption("N/A (no analyst rating data)")
        else:
            months = [f"{m:%b %Y}" for m in rec["month"]]
            series = [(RATING_LABELS[c], [int(v) for v in rec[c]]) for c in RATING_COLS]
            st.plotly_chart(charts.stacked_ratings(months, series), key=f"{o.symbol}_ratings",
                            config={"displayModeBar": False})
            ui.badge(_demo(o.rec_source or "yfinance", "Analyst rating counts"))
    with c2:
        cs = o.consensus
        if cs:
            st.metric("Analysts covering (latest month)", f"{cs['total']}")
            counts = cs["counts"]
            pos = counts["strongBuy"] + counts["buy"]
            neg = counts["sell"] + counts["strongSell"]
            st.caption(f"Wall Street analysts' ratings: {pos} positive (buy / strong buy), {counts['hold']} hold, "
                       f"{neg} negative (sell / strong sell). Average score {cs['mean_score']:.2f} on a scale from "
                       "1 (strong buy) to 5 (strong sell).")
        tg = o.target
        if tg.get("mean"):
            st.metric("Analysts' mean price target", ui.fmt_money(tg["mean"]))
            st.caption(f"Range {ui.fmt_money(tg.get('low'))} – {ui.fmt_money(tg.get('high'))}. Opinion, not a forecast.")
    st.markdown("##### Recent rating changes by Wall Street firms")
    up = o.upgrades
    if up.empty:
        st.caption("No recent rating changes.")
    else:
        st.dataframe(up, hide_index=True, width="stretch")
        ui.badge(_demo("yfinance", "Upgrades and downgrades (Yahoo Finance)"))


def _short(o: OwnershipData) -> None:
    st.markdown("##### Short interest", help=tooltip("short_interest", ui.lang()))
    s = o.short
    c = st.columns(3)
    c[0].metric("Short % of float", f"{s['pct_float']:.2%}" if s.get("pct_float") is not None else "N/A",
                help=tooltip("short_interest", ui.lang()))
    c[1].metric("Days to cover", f"{s['days_to_cover']:.1f}" if s.get("days_to_cover") is not None else "N/A",
                help=tooltip("short_interest", ui.lang()))
    c[2].metric("Shares sold short", f"{s['shares_short'] / 1e6:,.1f}M" if s.get("shares_short") else "N/A")
    if s.get("as_of"):
        st.caption(f"As of {s['as_of']:%d %b %Y} (short interest is reported twice a month, with a delay).")
    ui.badge(_demo("yfinance", "Short interest (exchange data via Yahoo Finance)"))


def render_ownership_tab(o: Optional[OwnershipData]) -> None:
    if o is None:
        st.info("Ownership data is not available right now.")
        return
    if ui.safe_mode():
        st.info(f"{ui.SAFE_MODE_TEXT}. Holders, insider trades, analyst ratings and short interest come from demo "
                "sources here. (Insider trades are also available licensed-safe from SEC Form 4, see News & Filings.)")
        return
    _holders(o)
    st.divider()
    _insiders(o)
    st.divider()
    _analysts(o)
    st.divider()
    _short(o)
