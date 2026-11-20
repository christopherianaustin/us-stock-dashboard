"""Tab 5: Valuation - ratio cards, 5-year history, peers, fair value estimates."""
from __future__ import annotations

from typing import Optional

import pandas as pd
import streamlit as st

from app.components import charts, ui
from core.analysis import Analysis
from core.glossary import tooltip
from core.models import DataPoint, LicenseTag, Source
from core.ratios import METRICS
from core.valuation import dcf, dcf_scenarios, percentile_sentence

CARDS = ["pe", "forward_pe", "peg", "ps", "pb", "ev_ebitda", "ev_revenue", "p_fcf", "fcf_yield", "earnings_yield"]
HIST = {"pe": "P/E", "ps": "P/S", "ev_ebitda": "EV/EBITDA"}
PEER_METRICS = {"pe": ("P/E", "x"), "ps": ("P/S", "x"), "ev_ebitda": ("EV/EBITDA", "x"),
                "revenue_growth": ("Revenue growth", "pct"), "net_margin": ("Net margin", "pct"),
                "roe": ("ROE", "pct"), "market_cap": ("Market cap", "money")}
OUR_PEER_VALUE = {"pe": "pe", "ps": "ps", "ev_ebitda": "ev_ebitda", "revenue_growth": "revenue_yoy",
                  "net_margin": "net_margin", "roe": "roe"}


def _demo_badge(note: str) -> None:
    ui.badge(DataPoint(value=1, source=Source.YFINANCE, license_tag=LicenseTag.DEMO_ONLY, note=note))


def _cards(a: Analysis) -> None:
    st.markdown("##### Valuation ratios: now vs its own 5-year median vs peers",
                help="Each card compares today's value with the stock's own 5-year history and with the median of "
                     "similar companies. Lower usually means cheaper, but cheap stocks can be cheap for a reason.")
    for row in (CARDS[:5], CARDS[5:]):
        cols = st.columns(5)
        for col, name in zip(cols, row):
            label, unit, _, gkey = METRICS[name]
            dp = a.snapshot[name]
            subs = []
            if name in a.stats and a.stats[name].median is not None:
                subs.append(f"5y median {ui.fmt_unit(a.stats[name].median, unit)}")
            if name in a.peer_medians and a.peer_medians.get(name) is not None and not ui.safe_mode():
                subs.append(f"peers {ui.fmt_unit(a.peer_medians[name], unit)}")
            with col:
                ui.metric_dp(label, dp, unit, gkey, " · ".join(subs) or None)


def _history(a: Analysis) -> None:
    h = a.history
    lic_dp = DataPoint(value=1, source=Source.CALCULATED, license_tag=a.history_license, derived=True,
                       note="Daily price vs TTM financials known on that day (SEC filing dates)")
    if ui.hidden_by_safe_mode(lic_dp):
        st.info(f"Valuation history: {ui.SAFE_MODE_TEXT} (needs a licensed daily price history).")
        return
    if h.empty or h["pe"].dropna().empty and h["ps"].dropna().empty:
        st.caption("Valuation history: N/A (needs 5 years of prices and financial data)")
        return
    st.markdown("##### P/E over the last 5 years: above the gray line = more expensive than usual",
                help=tooltip("valuation_history", ui.lang()))
    pe = h["pe"].dropna()
    if not pe.empty:
        s = a.stats["pe"]
        st.plotly_chart(charts.history_band(pe.index, pe, "P/E", s.median, s.std), key=f"{a.symbol}_pe_hist",
                        config={"displayModeBar": False})
    else:
        st.caption(f"P/E history: N/A ({a.snapshot['pe'].na_reason or 'earnings were negative or missing'})")
    ui.badge(lic_dp)

    c1, c2 = st.columns(2)
    for col, key in ((c1, "ps"), (c2, "ev_ebitda")):
        with col:
            s = h[key].dropna() if key in h else pd.Series(dtype=float)
            st.markdown(f"##### {HIST[key]} over 5 years", help=tooltip("valuation_history", ui.lang()))
            if s.empty:
                reason = a.snapshot[key].na_reason or "not enough data"
                st.caption(f"N/A ({reason})")
                continue
            stt = a.stats[key]
            st.plotly_chart(charts.history_band(s.index, s, HIST[key], stt.median, stt.std, height=260, band=False),
                            key=f"{a.symbol}_{key}_hist", config={"displayModeBar": False})

    items = [(HIST[k], a.stats[k].percentile) for k in HIST if a.stats[k].percentile is not None]
    if items:
        st.markdown("##### Cheaper or more expensive than its own history?",
                    help="The bar shows the share of trading days in the last 5 years when the ratio was LOWER "
                         "than today. 90% = more expensive than on 90% of days.")
        st.plotly_chart(charts.percentile_bars(items, height=90 + 45 * len(items)), key=f"{a.symbol}_pctl",
                        config={"displayModeBar": False})
        for k in HIST:
            sent = percentile_sentence(HIST[k], a.stats[k])
            if sent:
                st.caption("• " + sent)


def _peers(a: Analysis) -> None:
    st.markdown("##### Peer comparison", help=tooltip("peers", ui.lang()))
    if ui.safe_mode():
        st.info(f"Peer comparison: {ui.SAFE_MODE_TEXT} (peer list and peer ratios come from demo sources).")
        return
    if a.peers.empty:
        st.caption("N/A (no peer list available for this company)")
        return
    ours = {"ticker": a.symbol, "name": "(this stock, our calculation)"}
    for k, snap_key in OUR_PEER_VALUE.items():
        dp = a.snapshot.get(snap_key)
        ours[k] = dp.value if dp is not None and dp.available else None
    ours["market_cap"] = None
    peers = a.peers.copy()
    table = pd.concat([pd.DataFrame([ours]), peers], ignore_index=True)
    med = {"ticker": "Peer median", "name": "", **{k: a.peer_medians.get(k) for k in PEER_METRICS}}
    display = pd.concat([table, pd.DataFrame([med])], ignore_index=True)
    fmt = display.copy()
    for k, (label, kind) in PEER_METRICS.items():
        unit = {"x": "x", "pct": "ratio", "money": "USD"}[kind]
        fmt[label] = display[k].map(lambda v, u=unit: ui.fmt_unit(v, u) if v is not None and not pd.isna(v) else "N/A")
    fmt = fmt[["ticker", "name"] + [lab for lab, _ in PEER_METRICS.values()]]
    st.dataframe(fmt, hide_index=True, width="stretch")
    st.caption("Peers' ratios come from Yahoo Finance; this stock's row uses our SEC-based calculation, so small "
               "method differences are possible. Revenue growth = latest quarter vs a year earlier.")
    c1, c2 = st.columns([1, 2])
    with c1:
        metric = st.selectbox("Compare by", list(PEER_METRICS)[:6], format_func=lambda k: PEER_METRICS[k][0],
                              key=f"peer_metric_{a.symbol}")
    label, kind = PEER_METRICS[metric]
    rows = table[["ticker", metric]].dropna()
    if not rows.empty:
        st.plotly_chart(charts.peer_bars(list(rows["ticker"]), list(rows[metric]), a.symbol,
                                         a.peer_medians.get(metric), kind), key=f"{a.symbol}_peerbar_{metric}",
                        config={"displayModeBar": False})
    _demo_badge("Peer list (Finnhub/Yahoo) and peer ratios (Yahoo Finance)")
    st.download_button("Download CSV", display.to_csv(index=False).encode("utf-8"),
                       file_name=f"{a.symbol}_peers.csv", mime="text/csv", key=f"dl_peers_{a.symbol}")


def _fair_value(a: Analysis) -> None:
    st.markdown("#### Fair value estimates")
    st.warning("**Estimate based on assumptions. Not a prediction.** These formulas show what the price would be "
               "*if* the assumptions are right. Small changes in assumptions change the result a lot.", icon="⚠️")
    price = a.price
    rows: list[tuple[str, Optional[float], Optional[float], Optional[float]]] = []

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("##### Graham number", help=tooltip("graham", ui.lang()))
        g = a.graham
        if g.available:
            st.metric("Graham number (classic formula, estimate)", ui.fmt_money(g.value))
            if price:
                st.caption(f"Price is {price / g.value - 1:+.0%} vs the Graham number.")
            ui.badge(g)
            rows.append(("Graham number", None, g.value, None))
        else:
            st.caption(f"N/A ({g.na_reason})")
    with c2:
        st.markdown("##### Wall Street analysts' price targets", help=tooltip("target_upside", ui.lang()))
        est = a.estimates
        dp = a.snapshot["target_upside"]
        if ui.hidden_by_safe_mode(dp) or (ui.safe_mode() and est.target_mean):
            st.caption(ui.SAFE_MODE_TEXT)
        elif est.target_mean:
            st.metric("Mean analyst target", ui.fmt_money(est.target_mean),
                      delta=f"{dp.value:+.1%} vs price" if dp.available else None, delta_color="off")
            st.caption(f"Range: {ui.fmt_money(est.target_low)} – {ui.fmt_money(est.target_high)}. "
                       "Third-party opinion, not our view.")
            _demo_badge("Analyst price targets (Yahoo Finance)")
            rows.append(("Analyst targets", est.target_low, est.target_mean, est.target_high))
        else:
            st.caption("N/A (no analyst price targets available)")

    # ----- DCF -----
    d = a.dcf_inputs
    st.markdown("##### Simple DCF (discounted cash flow)", help=tooltip("dcf", ui.lang()))
    if d.get("not_meaningful"):
        st.caption(f"N/A ({d['not_meaningful']})")
    elif d["fcf0"] is None or d["fcf0"] <= 0:
        st.caption("N/A (a DCF needs positive free cash flow)")
    else:
        s1, s2, s3 = st.columns(3)
        g = s1.slider("Yearly FCF growth (next 5 years)", -10.0, 30.0, round(d["growth"] * 100, 1), 0.5,
                      format="%.1f%%", key=f"dcf_g_{a.symbol}",
                      help=f"Default: {d['growth_source']}, capped at 20%.") / 100
        r = s2.slider("Discount rate", 6.0, 15.0, d["discount"] * 100, 0.5, format="%.1f%%",
                      key=f"dcf_r_{a.symbol}", help="Your required yearly return. 10% is a common default.") / 100
        t = s3.slider("Terminal growth (after year 5)", 0.0, 4.0, d["terminal"] * 100, 0.25, format="%.2f%%",
                      key=f"dcf_t_{a.symbol}", help="Long-run growth forever after year 5. Usually 2-3%.") / 100
        scen = dcf_scenarios(d["fcf0"], g, r, t, d["net_debt"], d["shares"])
        base = scen["Base"]
        if base.per_share is None:
            st.caption(f"N/A ({base.reason})")
        else:
            m1, m2, m3 = st.columns(3)
            for col, name, delta in ((m1, "Bear", -5), (m2, "Base", 0), (m3, "Bull", 5)):
                res = scen[name]
                with col:
                    if res.per_share is None:
                        st.metric(f"{name} case", "N/A")
                        continue
                    vs = f"{res.per_share / price - 1:+.0%} vs price" if price else None
                    st.metric(f"{name} case (growth {g * 100 + delta:.1f}%)", ui.fmt_money(res.per_share),
                              delta=vs, delta_color="off")
            st.caption(f"Assumptions: starting free cash flow {ui.fmt_big_money(d['fcf0'])} (last 12 months), "
                       f"{g * 100:.1f}% growth for 5 years, {r * 100:.1f}% discount rate, {t * 100:.2f}% terminal "
                       f"growth, net debt {ui.fmt_big_money(d['net_debt'])}, {d['shares'] / 1e9:,.2f}B shares. "
                       "Bear / bull = growth −5 / +5 percentage points.")
            dcf_dp = DataPoint(value=base.per_share, source=Source.CALCULATED, derived=True,
                               license_tag=LicenseTag.CALCULATED_SAFE if d["growth_source"].startswith("3-year")
                               else LicenseTag.DEMO_ONLY, note="DCF estimate")
            ui.badge(dcf_dp)
            vals = [x.per_share for x in scen.values() if x.per_share is not None]
            rows.append(("DCF (bear–bull)", min(vals), base.per_share, max(vals)))

    if rows and price:
        st.markdown("##### Today's price vs these estimates")
        st.plotly_chart(charts.fair_value_chart(price, rows, height=110 + 55 * len(rows)),
                        key=f"{a.symbol}_fairvalue", config={"displayModeBar": False})
        st.caption("Dots = central estimate, bars = range. Estimates, not predictions.")


def _yahoo_check(a: Analysis) -> None:
    df = a.yahoo_compare
    if df.empty:
        return
    with st.expander("Data check: our ratios vs Yahoo Finance"):
        st.caption("Differences usually come from timing (Yahoo may include a quarter that is not yet filed with "
                   "the SEC) or definitions (e.g. Yahoo counts leases as debt and uses a different ROA formula).")
        out = df.copy()
        units = {k: METRICS[k][1] for k in METRICS}
        out["metric"] = df["metric"].map(lambda k: METRICS.get(k, (k,))[0])
        out["ours"] = [ui.fmt_unit(v, units.get(k, "x")) for v, k in zip(df["ours"], df["metric"])]
        out["yahoo"] = [ui.fmt_unit(v, units.get(k, "x")) for v, k in zip(df["yahoo"], df["metric"])]
        out["difference"] = df["difference"].map(lambda v: "—" if v is None or pd.isna(v) else f"{v * 100:+.1f}%")
        st.dataframe(out, hide_index=True, width="stretch")


def render_valuation_tab(a: Optional[Analysis]) -> None:
    if a is None:
        st.info("Valuation needs financial statements, which are not available for this company.")
        return
    for w in a.warnings:
        st.warning(w, icon="⚠️")
    _cards(a)
    st.divider()
    _history(a)
    st.divider()
    _peers(a)
    st.divider()
    _fair_value(a)
    _yahoo_check(a)
