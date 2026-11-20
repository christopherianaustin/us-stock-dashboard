"""Tab 11: Data coverage report - every field, its source, license tag and whether it loaded."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from app.components import ui
from core.coverage import coverage_rows, coverage_summary

LICENSE_LABEL = {"COMMERCIAL_OK": "🟢 Licensed-safe", "CALCULATED_SAFE": "🔵 Calculated", "DEMO_ONLY": "🟠 Demo data"}


def render_coverage_tab(bundle) -> None:
    rows = coverage_rows(bundle, ui.safe_mode())
    summ = coverage_summary(rows)
    st.markdown("#### Data coverage report",
                help="Every field the dashboard uses: where it comes from, whether it may be used commercially, "
                     "whether it loaded for this ticker, and which licensed source could replace demo data. "
                     "The same report is available from the API at /coverage/{ticker}; DATA_SOURCES.md lists the "
                     "replacement vendors.")
    c = st.columns(4)
    c[0].metric("Fields loaded", f"{summ['loaded']} / {summ['fields']}")
    c[1].metric("🟢 Licensed-safe", f"{summ['COMMERCIAL_OK']['loaded']} / {summ['COMMERCIAL_OK']['fields']}")
    c[2].metric("🔵 Calculated", f"{summ['CALCULATED_SAFE']['loaded']} / {summ['CALCULATED_SAFE']['fields']}")
    c[3].metric("🟠 Demo data", f"{summ['DEMO_ONLY']['loaded']} / {summ['DEMO_ONLY']['fields']}")
    st.caption("🟠 Demo-data fields must be replaced by a licensed vendor (or the Nanovest price feed) before a "
               "commercial launch. Turn on Production-safe mode in the sidebar to see the app without them.")

    df = pd.DataFrame(rows)
    f1, f2, f3 = st.columns([2, 1.3, 1])
    with f1:
        sections = st.multiselect("Sections", list(dict.fromkeys(df["section"])), key="cov_sections",
                                  placeholder="All sections")
    with f2:
        lic = st.multiselect("License", list(LICENSE_LABEL), format_func=LICENSE_LABEL.get, key="cov_license",
                             placeholder="All licenses")
    with f3:
        missing_only = st.toggle("Only fields not loaded", key="cov_missing")
    view = df
    if sections:
        view = view[view["section"].isin(sections)]
    if lic:
        view = view[view["license_tag"].isin(lic)]
    if missing_only:
        view = view[~view["loaded"]]
    show = pd.DataFrame({
        "section": view["section"], "field": view["field"], "source": view["source"],
        "license": view["license_tag"].map(LICENSE_LABEL),
        "loaded": view["loaded"].map({True: "✅ yes", False: "— no"}),
        "value / note": [p if p else n for p, n in zip(view["preview"], view["note"])],
        "where it comes from": view["where"], "production replacement": view["replacement"],
    })
    st.dataframe(show, hide_index=True, width="stretch", height=min(36 * (len(show) + 1), 720))
    st.download_button("Download CSV", df.to_csv(index=False).encode("utf-8"),
                       file_name=f"{bundle.resolved.symbol}_data_coverage.csv", mime="text/csv", key="dl_coverage")
