"""Tab 4: Financials (Income Statement, Balance Sheet, Cash Flow)."""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd
import streamlit as st

from app.components import charts, ui
from core.financials import DERIVED_FIELDS, Financials, field_label, field_specs
from core.glossary import tooltip
from core.models import DataPoint, LicenseTag, Source

INCOME_ROWS = ["revenue", "cost_of_revenue", "gross_profit", "rnd", "sga", "operating_income", "ebitda",
               "interest_expense", "pretax_income", "income_tax", "net_income", "eps_basic", "eps_diluted",
               "diluted_shares", "gross_margin", "operating_margin", "ebitda_margin", "net_margin",
               "revenue_yoy", "eps_yoy", "effective_tax_rate"]
BALANCE_ROWS = ["cash", "short_term_investments", "receivables", "inventory", "current_assets", "total_assets",
                "current_liabilities", "short_term_debt", "long_term_debt", "total_debt", "total_liabilities",
                "equity", "retained_earnings", "net_debt", "current_ratio", "debt_to_equity", "shares_outstanding"]
CASHFLOW_ROWS = ["operating_cash_flow", "capex", "fcf", "fcf_margin", "da", "dividends_paid", "buybacks",
                 "shareholder_returns", "dividends_per_share"]


# ---------- formatting ----------
def _unit(field: str) -> str:
    if field in field_specs():
        return field_specs()[field].unit
    return DERIVED_FIELDS.get(field, ("", "", "USD"))[2]


def fmt_value(v, unit: str) -> str:
    if v is None or pd.isna(v):
        return "N/A"
    if unit == "USD":
        a = abs(v)
        for div, suf in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
            if a >= div:
                return f"{'-' if v < 0 else ''}${a / div:,.2f}{suf}"
        return f"{'-' if v < 0 else ''}${a:,.0f}"
    if unit == "USD/shares":
        return f"{'-' if v < 0 else ''}${abs(v):,.2f}"
    if unit == "shares":
        return f"{v / 1e9:,.2f}B" if abs(v) >= 1e9 else f"{v / 1e6:,.1f}M"
    if unit == "ratio":
        return f"{v * 100:,.1f}%"
    if unit == "x":
        return f"{v:,.2f}x"
    return f"{v:,.2f}"


# ---------- helpers ----------
class _Ctx:
    def __init__(self, fin: Financials, ptype: str, n: int):
        self.fin, self.ptype = fin, ptype
        self.periods = fin.periods(ptype, n)
        self.since = self.periods["period_end"].min() if not self.periods.empty else None
        self.x = [f"{lab}<br><span style='font-size:10px'>{pe:%d %b %y}</span>"
                  for lab, pe in zip(self.periods["label"], self.periods["period_end"])]

    def vals(self, field: str) -> list[Optional[float]]:
        s = self.fin.series(field, self.ptype)
        return [None if pe not in s.index or pd.isna(s[pe]) else float(s[pe]) for pe in self.periods["period_end"]]

    def has(self, field: str) -> bool:
        return any(v is not None for v in self.vals(field))

    def reason(self, field: str) -> str:
        return self.fin.na_reason(field, self.since) or "No data for these periods"


def _license_badge(fin: Financials, fields: list[str]) -> None:
    lic = fin.license_for(fields)
    src = Source.SEC if fin.source == Source.SEC.value else Source.YFINANCE
    if lic == LicenseTag.CALCULATED_SAFE:
        src = Source.CALCULATED if fin.source == Source.SEC.value else src
    dp = DataPoint(value=1, source=src, license_tag=lic,
                   note=f"Based on {fin.source} filings" if fin.source == Source.SEC.value else "yfinance statements")
    ui.badge(dp)


def _chart(ctx: _Ctx, key: str, title: str, gkeys: list[str], fig, fields: list[str],
           missing: Optional[list[str]] = None) -> None:
    help_text = "\n\n---\n\n".join(t for t in (tooltip(k, ui.lang()) for k in gkeys) if t) or None
    st.markdown(f"##### {title}", help=help_text)
    st.plotly_chart(fig, key=f"{ctx.fin.symbol}_{ctx.ptype}_{key}", config={"displayModeBar": False})
    _license_badge(ctx.fin, fields)
    for f in missing or []:
        st.caption(f"{field_label(f)}: N/A ({ctx.reason(f)})")


def _present(ctx: _Ctx, fields: list[str]) -> tuple[list[tuple[str, list]], list[str]]:
    series, missing = [], []
    for f in fields:
        if ctx.has(f):
            series.append((field_label(f).replace(" (calculated)", ""), ctx.vals(f)))
        else:
            missing.append(f)
    return series, missing


def _statement_table(ctx: _Ctx, rows: list[str], name: str, with_ttm: bool) -> None:
    fin, periods = ctx.fin, ctx.periods
    newest_first = periods.iloc[::-1]
    col_names = [f"{lab} ({pe:%Y-%m-%d})" for lab, pe in zip(newest_first["label"], newest_first["period_end"])]
    table, reasons = {}, []
    for f in rows:
        r = fin.rows(f, ctx.ptype)
        unit = _unit(f)
        cells = []
        if with_ttm:
            t = fin.ttm(f) if unit in ("USD", "USD/shares") else None
            cells.append((fmt_value(t["value"], unit) + " ✱") if t else "—")
        for pe in newest_first["period_end"]:
            if pe in r.index and not pd.isna(r.loc[pe, "value"]):
                row = r.loc[pe]
                cells.append(fmt_value(row["value"], unit) + (" ✱" if row["derived"] else ""))
            else:
                cells.append("N/A")
        if all(c == "N/A" for c in cells[1 if with_ttm else 0:]):
            reasons.append(f"**{field_label(f)}**: {ctx.reason(f)}")
        table[field_label(f)] = cells
    cols = (["TTM"] if with_ttm else []) + col_names
    df = pd.DataFrame.from_dict(table, orient="index", columns=cols)
    st.markdown(f"##### Full {name.lower()}", help=tooltip("derived", ui.lang()))
    st.dataframe(df, width="stretch", height=min(38 * (len(df) + 1), 820))
    st.caption("✱ = derived (calculated by us, e.g. Q4 = full year minus Q1–Q3, or quarterly cash flow from "
               "year-to-date figures)." + (" TTM = trailing twelve months (sum of the last 4 quarters)." if with_ttm else ""))
    if reasons:
        with st.expander(f"Why some rows show N/A ({len(reasons)})"):
            for r in reasons:
                st.markdown(f"- {r}")
    raw = fin.tidy[(fin.tidy["field"].isin(rows)) & (fin.tidy["period_type"] == ctx.ptype)
                   & (fin.tidy["period_end"].isin(periods["period_end"]))].copy()
    raw["label"] = raw["field"].map(field_label)
    raw = raw.sort_values(["field", "period_end"])
    st.download_button("Download CSV", raw.to_csv(index=False).encode("utf-8"),
                       file_name=f"{fin.symbol}_{name.lower().replace(' ', '_')}_{'quarterly' if ctx.ptype == 'Q' else 'annual'}.csv",
                       mime="text/csv", key=f"dl_{fin.symbol}_{name}_{ctx.ptype}")


# ---------- sub-tabs ----------
def _income(ctx: _Ctx) -> None:
    if ctx.has("revenue"):
        _chart(ctx, "rev_margin", "Revenue, and how much of it becomes profit (net margin)", ["revenue", "margins"],
               charts.bars_over_line(ctx.x, "Revenue", ctx.vals("revenue"), "Net margin", ctx.vals("net_margin")),
               ["revenue", "net_income"])
    series, missing = _present(ctx, ["revenue", "gross_profit", "ebitda", "pretax_income", "net_income"])
    if series:
        _chart(ctx, "waterfall", "From revenue to profit: what is left at each step", ["gross_profit", "ebitda", "net_income"],
               charts.bars(ctx.x, series), ["revenue", "gross_profit", "operating_income", "da", "pretax_income", "net_income"],
               missing)
    series, missing = _present(ctx, ["gross_margin", "operating_margin", "ebitda_margin", "net_margin"])
    if series:
        _chart(ctx, "margins", "Profit margins: rising lines mean the company keeps more of each dollar", ["margins"],
               charts.lines(ctx.x, series, kind="pct"), ["revenue", "gross_profit", "operating_income", "net_income"], missing)
    c1, c2 = st.columns(2)
    with c1:
        if ctx.has("revenue_yoy"):
            _chart(ctx, "rev_yoy", "Revenue growth vs a year earlier", ["growth"],
                   charts.signed_bars(ctx.x, ctx.vals("revenue_yoy"), "Revenue YoY"), ["revenue"])
        else:
            st.caption("Revenue growth: N/A (needs the same period a year earlier)")
    with c2:
        if ctx.has("eps_yoy"):
            _chart(ctx, "eps_yoy", "EPS growth vs a year earlier", ["growth", "eps_diluted"],
                   charts.signed_bars(ctx.x, ctx.vals("eps_yoy"), "EPS YoY"), ["eps_diluted"])
        elif not ctx.has("eps_diluted"):
            st.caption(f"EPS growth: N/A ({ctx.reason('eps_diluted')})")
        else:
            st.caption("EPS growth: N/A (needs the same period a year earlier)")
    series, missing = _present(ctx, ["cogs_pct", "rnd_pct", "sga_pct"])
    if series:
        _chart(ctx, "expenses", "Where the revenue goes: main costs as % of revenue", ["expense_breakdown"],
               charts.bars(ctx.x, series, kind="pct", barmode="stack"), ["revenue", "cost_of_revenue", "rnd", "sga"], missing)
    _statement_table(ctx, INCOME_ROWS, "Income statement", with_ttm=ctx.ptype == "Q")


def _balance(ctx: _Ctx) -> None:
    eq_field = "equity_incl_nci" if ctx.has("equity_incl_nci") else "equity"
    if ctx.has("total_assets"):
        _chart(ctx, "bs", "What the company owns (assets) vs what it owes (liabilities) and shareholders' equity",
               ["total_assets"],
               charts.assets_vs_liabilities_equity(ctx.x, ctx.vals("total_assets"), ctx.vals("total_liabilities"),
                                                   ctx.vals(eq_field)),
               ["total_assets", "total_liabilities", eq_field])
    cash = [None if c is None and s is None else (c or 0) + (s or 0)
            for c, s in zip(ctx.vals("cash"), ctx.vals("short_term_investments"))]
    if ctx.has("total_debt") or any(v is not None for v in cash):
        _chart(ctx, "cash_debt", "Cash vs debt (line below zero = more cash than debt)", ["net_debt", "total_debt"],
               charts.bars_with_line(ctx.x, [("Cash & short-term investments", cash), ("Total debt", ctx.vals("total_debt"))],
                                     "Net debt", ctx.vals("net_debt")),
               ["cash", "short_term_investments", "short_term_debt", "long_term_debt"],
               [f for f in ("total_debt",) if not ctx.has(f)])
    series, missing = _present(ctx, ["current_ratio", "debt_to_equity"])
    if series:
        _chart(ctx, "liq", "Liquidity (current ratio) and leverage (debt to equity)", ["current_ratio", "debt_to_equity"],
               charts.lines(ctx.x, series, kind="x"), ["current_assets", "current_liabilities", "long_term_debt", "equity"],
               missing)
    else:
        for f in missing:
            st.caption(f"{field_label(f)}: N/A ({ctx.reason(f)})")
    _statement_table(ctx, BALANCE_ROWS, "Balance sheet", with_ttm=False)


def _cashflow(ctx: _Ctx) -> None:
    series, missing = _present(ctx, ["operating_cash_flow", "capex", "fcf"])
    if series:
        _chart(ctx, "cf", "Cash generated, cash invested, and free cash flow left over",
               ["operating_cash_flow", "capex", "fcf"], charts.bars(ctx.x, series),
               ["operating_cash_flow", "capex"], missing)
    series, missing = _present(ctx, ["fcf", "net_income"])
    if len(series) == 2:
        _chart(ctx, "quality", "Earnings quality: free cash flow vs net income (FCF above profit is a good sign)",
               ["fcf", "net_income"], charts.lines(ctx.x, series, kind="money"),
               ["operating_cash_flow", "capex", "net_income"])
    series, missing = _present(ctx, ["dividends_paid", "buybacks"])
    if series:
        _chart(ctx, "returns", "Cash returned to shareholders (dividends + buybacks)", ["shareholder_returns"],
               charts.bars(ctx.x, series, barmode="stack"), ["dividends_paid", "buybacks"], missing)
    else:
        st.caption("Shareholder returns: N/A (no dividends or buybacks reported)")
    _statement_table(ctx, CASHFLOW_ROWS, "Cash flow statement", with_ttm=ctx.ptype == "Q")


def _data_quality(fin: Financials) -> None:
    if fin.crosscheck is None or fin.crosscheck.empty or ui.safe_mode():
        return
    bad = int((fin.crosscheck["status"] == "Differs > 2%").sum())
    with st.expander(f"Data quality check: SEC vs yfinance, last 4 quarters ({bad} difference(s) above 2%)"):
        st.caption("We compare official SEC numbers with yfinance. Small differences are normal; "
                   "bigger ones usually mean the two sources define the item differently. SEC is the official source.")
        df = fin.crosscheck.copy()
        for c in ("SEC EDGAR", "yfinance"):
            df[c] = df[c].map(lambda v: fmt_value(v, "USD"))
        df["difference"] = df["difference"].map(lambda v: "—" if v is None or pd.isna(v) else f"{v * 100:+.2f}%")
        st.dataframe(df, hide_index=True, width="stretch")


def render_financials_tab(fin: Optional[Financials]) -> None:
    if fin is None or not fin.available:
        st.info("Financial statements are not available for this company "
                "(no data from SEC EDGAR or yfinance).")
        return
    if ui.safe_mode() and fin.source != Source.SEC.value:
        st.info(f"{ui.SAFE_MODE_TEXT}. SEC EDGAR has no usable financial data for this company, "
                "and the backup source (yfinance) is demo-only.")
        return
    for w in fin.warnings:
        st.warning(w, icon="⚠️")

    c1, c2 = st.columns([1, 2], vertical_alignment="center")
    with c1:
        period = st.segmented_control("Period", ["Quarterly", "Annual"], default="Quarterly", required=True,
                                      key="fin_period", label_visibility="collapsed")
    with c2:
        src = "SEC EDGAR (official 10-Q / 10-K filings)" if fin.source == Source.SEC.value else "yfinance (demo only)"
        st.caption(f"Source: {src}. Quarters are labeled by the company's own fiscal year, with the period end date.")
    ptype = "Q" if period == "Quarterly" else "FY"
    ctx = _Ctx(fin, ptype, 12 if ptype == "Q" else 10)
    if ctx.periods.empty:
        st.info("No periods available.")
        return

    inc, bal, cf = st.tabs(["Income Statement", "Balance Sheet", "Cash Flow"])
    with inc:
        _income(ctx)
    with bal:
        _balance(ctx)
    with cf:
        _cashflow(ctx)
    _data_quality(fin)
