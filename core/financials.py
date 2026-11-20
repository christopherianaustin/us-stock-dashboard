"""Build quarterly and annual financial statements from SEC EDGAR XBRL facts.

Rules (SPEC Section 5):
  * Try XBRL tags in priority order, per period (config/xbrl_tags.yaml).
  * Duration facts (income, cash flow) vs instant facts (balance sheet).
  * Quarters = 80-100 day durations, years = 350-380 days.
  * Q4 is not filed: Q4 = full year - 9-month YTD (or - Q1 - Q2 - Q3). Marked derived.
  * 10-Q cash flow is year-to-date: single quarter = YTD - previous YTD. Marked derived.
  * EPS Q4 = Q4 net income / Q4 diluted shares (not subtraction).
  * Duplicates / restatements: prefer facts with a `frame`, else the most recently filed.
Output is one tidy table:
  field, period_end, period_start, period_type (Q/FY), fiscal_year, fiscal_quarter, value,
  unit, source, derived, method, license_tag, tag, filed, first_filed
`first_filed` is when the value was first public (used later to avoid look-ahead bias).
"""
from __future__ import annotations

import functools
from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np
import pandas as pd
import yaml

from config.settings import CONFIG_DIR
from core.logging_setup import get_logger
from core.models import LicenseTag, Source

log = get_logger("financials")

QUARTER_DAYS = (80, 100)
ANNUAL_DAYS = (350, 380)
PERIODIC_FORM_PREFIXES = ("10-K", "10-Q", "20-F", "40-F")
DAY = pd.Timedelta(days=1)

COLUMNS = ["field", "period_end", "period_start", "period_type", "fiscal_year", "fiscal_quarter",
           "value", "unit", "source", "derived", "method", "license_tag", "tag", "filed", "first_filed"]


# --------------------------------------------------------------------------- config
@dataclass(frozen=True)
class FieldSpec:
    name: str
    label: str
    statement: str
    kind: str
    unit: str
    tags: tuple[tuple[str, str], ...]
    special: Optional[str] = None


@functools.lru_cache(maxsize=1)
def field_specs() -> dict[str, FieldSpec]:
    with open(CONFIG_DIR / "xbrl_tags.yaml", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    out = {}
    for name, cfg in raw.items():
        tags = []
        for t in cfg["tags"]:
            tax, _, tag = t.rpartition(":")
            tags.append((tax or "us-gaap", tag))
        out[name] = FieldSpec(name=name, label=cfg["label"], statement=cfg["statement"], kind=cfg["kind"],
                              unit=cfg["unit"], tags=tuple(tags), special=cfg.get("special"))
    return out


# Calculated lines (label, statement, unit) - built from the base fields above
DERIVED_FIELDS: dict[str, tuple[str, str, str]] = {
    "ebitda": ("EBITDA (calculated)", "income", "USD"),
    "gross_margin": ("Gross margin", "income", "ratio"),
    "operating_margin": ("Operating margin", "income", "ratio"),
    "ebitda_margin": ("EBITDA margin", "income", "ratio"),
    "pretax_margin": ("EBT margin", "income", "ratio"),
    "net_margin": ("Net margin", "income", "ratio"),
    "effective_tax_rate": ("Effective tax rate", "income", "ratio"),
    "cogs_pct": ("Cost of revenue % of revenue", "income", "ratio"),
    "rnd_pct": ("R&D % of revenue", "income", "ratio"),
    "sga_pct": ("SG&A % of revenue", "income", "ratio"),
    "revenue_yoy": ("Revenue growth YoY", "income", "ratio"),
    "revenue_qoq": ("Revenue growth QoQ", "income", "ratio"),
    "eps_yoy": ("EPS growth YoY", "income", "ratio"),
    "total_debt": ("Total debt", "balance", "USD"),
    "net_debt": ("Net debt", "balance", "USD"),
    "current_ratio": ("Current ratio", "balance", "x"),
    "debt_to_equity": ("Debt to equity", "balance", "x"),
    "fcf": ("Free cash flow", "cashflow", "USD"),
    "fcf_margin": ("FCF margin", "cashflow", "ratio"),
    "shareholder_returns": ("Shareholder returns (dividends + buybacks)", "cashflow", "USD"),
}

# Fields that do not apply to banks and insurers, with the reason shown to users
FINANCIAL_CO_NA = {
    "cost_of_revenue": "Banks and insurers don't have a cost of revenue",
    "gross_profit": "Banks and insurers don't have a cost of revenue, so gross profit doesn't apply",
    "gross_margin": "Banks and insurers don't have a cost of revenue, so gross margin doesn't apply",
    "cogs_pct": "Banks and insurers don't have a cost of revenue",
    "ebitda": "EBITDA is not meaningful for banks and insurers (interest is their core business)",
    "ebitda_margin": "EBITDA is not meaningful for banks and insurers",
    "operating_income": "Banks and insurers usually don't report operating income",
    "operating_margin": "Banks and insurers usually don't report operating income",
    "current_assets": "Banks and insurers don't split assets into current / non-current",
    "current_liabilities": "Banks and insurers don't split liabilities into current / non-current",
    "current_ratio": "Not meaningful for banks and insurers (no current assets / liabilities)",
    "inventory": "Banks and insurers don't hold inventory",
}


def field_label(name: str) -> str:
    if name in field_specs():
        return field_specs()[name].label
    return DERIVED_FIELDS.get(name, (name,))[0]


# --------------------------------------------------------------------------- fiscal calendar
def filing_periods(facts: dict) -> dict[str, dict[str, Any]]:
    """accession -> {fy, fp, form, filed, period_end}. The filing's own period end is the
    latest end date among its duration facts (comparatives are always earlier)."""
    out: dict[str, dict[str, Any]] = {}
    for concept in (facts.get("facts", {}).get("us-gaap") or {}).values():
        for rows in concept.get("units", {}).values():
            for r in rows:
                accn = r.get("accn")
                if not accn or "start" not in r:
                    continue
                a = out.get(accn)
                if a is None:
                    out[accn] = {"fy": r.get("fy"), "fp": r.get("fp"), "form": r.get("form") or "",
                                 "filed": r.get("filed"), "period_end": r["end"]}
                elif r["end"] > a["period_end"]:
                    a["period_end"] = r["end"]
    return out


class FiscalCalendar:
    """Turns a period end date into (fiscal_year, fiscal_quarter) using the company's own
    filings, so non-calendar years (AAPL, NVDA, MSFT) are labeled correctly."""

    def __init__(self, fy_ends: dict[pd.Timestamp, int], q_ends: dict[pd.Timestamp, tuple[int, int]]):
        self.fy_ends = dict(sorted(fy_ends.items()))
        self.q_ends = q_ends

    @classmethod
    def from_filings(cls, periods: dict[str, dict[str, Any]]) -> "FiscalCalendar":
        fy_ends: dict[pd.Timestamp, int] = {}
        q_ends: dict[pd.Timestamp, tuple[int, int]] = {}
        for a in sorted(periods.values(), key=lambda x: x.get("filed") or ""):
            if not a.get("fy") or not a["form"].startswith(PERIODIC_FORM_PREFIXES) or a["form"].endswith("/A"):
                continue
            end = pd.Timestamp(a["period_end"])
            if a["fp"] == "FY":
                fy_ends[end] = int(a["fy"])
            elif a["fp"] in ("Q1", "Q2", "Q3"):
                q_ends[end] = (int(a["fy"]), int(a["fp"][1]))
        return cls(fy_ends, q_ends)

    @classmethod
    def from_annual_ends(cls, ends: list[pd.Timestamp]) -> "FiscalCalendar":
        """Fallback (e.g. yfinance data): fiscal year = calendar year the year ends in."""
        return cls({pd.Timestamp(e): pd.Timestamp(e).year for e in ends}, {})

    def label(self, end: pd.Timestamp, period_type: str) -> tuple[int, Optional[int]]:
        end = pd.Timestamp(end)
        if period_type == "FY":
            return (self.fy_ends[end] if end in self.fy_ends else self._estimate(end)[0]), None
        if end in self.fy_ends:
            return self.fy_ends[end], 4
        if end in self.q_ends:
            return self.q_ends[end]
        return self._estimate(end)

    def _estimate(self, end: pd.Timestamp) -> tuple[int, int]:
        if not self.fy_ends:
            return end.year, (end.month - 1) // 3 + 1
        ends = list(self.fy_ends)
        fy_end = next((e for e in ends if e >= end - pd.Timedelta(days=6)), None)
        if fy_end is None:  # after the last known year end: step forward one year at a time
            fy_end, fy = ends[-1], self.fy_ends[ends[-1]]
            while fy_end < end - pd.Timedelta(days=6):
                fy_end, fy = fy_end + pd.DateOffset(years=1), fy + 1
        else:
            fy = self.fy_ends[fy_end]
        prev_end = fy_end - pd.DateOffset(years=1)
        q = int(round((end - prev_end).days / 91.3))
        return fy, min(max(q, 1), 4)


def period_label(fiscal_year: int, fiscal_quarter: Optional[int], period_type: str) -> str:
    if period_type == "FY" or not fiscal_quarter or pd.isna(fiscal_quarter):
        return f"FY{int(fiscal_year)}"
    return f"Q{int(fiscal_quarter)} FY{int(fiscal_year) % 100:02d}"


# --------------------------------------------------------------------------- raw facts
def _collect(facts: dict, spec: FieldSpec) -> pd.DataFrame:
    recs = []
    for rank, (tax, tag) in enumerate(spec.tags):
        concept = (facts.get("facts", {}).get(tax) or {}).get(tag)
        if not concept:
            continue
        for r in concept.get("units", {}).get(spec.unit, []):
            form = r.get("form") or ""
            if not form.startswith(PERIODIC_FORM_PREFIXES):
                continue
            recs.append({"start": r.get("start"), "end": r["end"], "val": float(r["val"]),
                         "accn": r.get("accn"), "filed": r.get("filed"), "frame": r.get("frame"),
                         "tag": tag if tax == "us-gaap" else f"{tax}:{tag}", "rank": rank})
    df = pd.DataFrame(recs)
    if df.empty:
        return df
    df["end"] = pd.to_datetime(df["end"])
    df["start"] = pd.to_datetime(df["start"])
    df["filed"] = pd.to_datetime(df["filed"])
    return df


def dedupe(df: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    """One value per period: best tag first, then facts with a `frame`, then latest filed.
    Also records `first_filed` (earliest filing that reported this period)."""
    if df.empty:
        return df
    df = df.copy()
    df["has_frame"] = df["frame"].notna()
    first = df.groupby(keys, dropna=False)["filed"].min().rename("first_filed").reset_index()
    df = df.sort_values(["rank", "has_frame", "filed"], ascending=[True, False, False])
    out = df.drop_duplicates(keys, keep="first").drop(columns=["has_frame"])
    return out.merge(first, on=keys, how="left")


# --------------------------------------------------------------------------- duration logic
def _chain(quarters: dict, start: pd.Timestamp, end: pd.Timestamp) -> Optional[list[dict]]:
    """Consecutive quarters running from `start` up to one quarter before `end`."""
    picked, cursor = [], start
    for q in sorted(quarters.values(), key=lambda r: r["end"]):
        if q["end"] >= end:
            break
        if abs((q["start"] - cursor).days) <= 6:
            picked.append(q)
            cursor = q["end"] + DAY
    if not picked:
        return None
    gap = (end - picked[-1]["end"]).days
    return picked if QUARTER_DAYS[0] <= gap <= QUARTER_DAYS[1] else None


def quarters_from_durations(d: pd.DataFrame, additive: bool = True) -> dict[pd.Timestamp, dict]:
    """Single-quarter values keyed by period end.

    additive=True  (revenue, cash flow, ...): fill missing quarters from longer periods
                   using YTD subtraction or full-year minus earlier quarters.
    additive=False (EPS, weighted shares): only reported quarters; caller fills Q4.
    Input columns: start, end, val, filed, first_filed, tag.
    """
    if d.empty:
        return {}
    d = d.assign(days=(d["end"] - d["start"]).dt.days)
    quarters: dict[pd.Timestamp, dict] = {}
    q_rows = d[d["days"].between(*QUARTER_DAYS)].copy()
    q_rows["dist"] = (q_rows["days"] - 91).abs()
    for r in q_rows.sort_values("dist").drop_duplicates("end").itertuples():
        quarters[r.end] = {"start": r.start, "end": r.end, "val": r.val, "derived": False,
                           "method": "reported", "filed": r.filed, "first_filed": r.first_filed, "tag": r.tag}
    if not additive:
        return quarters

    longs = d[(d["days"] > QUARTER_DAYS[1]) & (d["days"] <= ANNUAL_DAYS[1])].sort_values("end")
    for L in longs.itertuples():
        if L.end in quarters:
            continue
        is_year = L.days >= ANNUAL_DAYS[0]
        prev = d[(d["start"] == L.start) & (d["end"] < L.end)]
        prev = prev[(L.end - prev["end"]).dt.days.between(*QUARTER_DAYS)]
        if not prev.empty:
            p = prev.iloc[0]
            val, q_start = L.val - p["val"], p["end"] + DAY
            filed, first = max(L.filed, p["filed"]), max(L.first_filed, p["first_filed"])
            method = "Full year minus 9-month YTD" if is_year else "YTD minus previous YTD"
        else:
            chain = _chain(quarters, L.start, L.end)
            if chain is None:
                continue
            val = L.val - sum(c["val"] for c in chain)
            q_start = chain[-1]["end"] + DAY
            filed = max([L.filed] + [c["filed"] for c in chain])
            first = max([L.first_filed] + [c["first_filed"] for c in chain])
            n = len(chain)
            method = ("Full year minus " if is_year else "YTD minus ") + "+".join(f"Q{i + 1}" for i in range(n))
        quarters[L.end] = {"start": q_start, "end": L.end, "val": val, "derived": True, "method": method,
                           "filed": filed, "first_filed": first, "tag": L.tag}
    return quarters


def annual_from_durations(d: pd.DataFrame) -> dict[pd.Timestamp, dict]:
    if d.empty:
        return {}
    d = d.assign(days=(d["end"] - d["start"]).dt.days)
    out = {}
    for r in d[d["days"].between(*ANNUAL_DAYS)].sort_values("end").itertuples():
        out[r.end] = {"start": r.start, "end": r.end, "val": r.val, "derived": False, "method": "reported",
                      "filed": r.filed, "first_filed": r.first_filed, "tag": r.tag}
    return out


def _fill_weighted_shares_q4(quarters: dict, annual: dict) -> None:
    """Weighted shares aren't additive. Approximation: Q4 = 4 x FY average - (Q1+Q2+Q3)."""
    for end, fy in annual.items():
        if end in quarters:
            continue
        chain = _chain(quarters, fy["start"], end)
        if not chain or len(chain) != 3:
            continue
        val = 4 * fy["val"] - sum(c["val"] for c in chain)
        if not (0.8 <= val / chain[-1]["val"] <= 1.2):  # implausible -> skip rather than show nonsense
            continue
        quarters[end] = {"start": chain[-1]["end"] + DAY, "end": end, "val": val, "derived": True,
                         "method": "4 x full-year average minus Q1-Q3 (approx.)",
                         "filed": fy["filed"], "first_filed": fy["first_filed"], "tag": fy["tag"]}


def _fill_eps_q4(eps_q: dict, eps_fy: dict, ni_q: dict, shares_q: dict, use_ratio: bool) -> None:
    """Q4 EPS = Q4 net income / Q4 diluted shares (preferred), else FY EPS - (Q1+Q2+Q3) EPS."""
    for end, fy in eps_fy.items():
        if end in eps_q:
            continue
        if use_ratio and end in ni_q and end in shares_q and shares_q[end]["val"]:
            ni, sh = ni_q[end], shares_q[end]
            eps_q[end] = {"start": ni["start"], "end": end, "val": ni["val"] / sh["val"], "derived": True,
                          "method": "Q4 net income / Q4 diluted shares",
                          "filed": max(ni["filed"], sh["filed"]),
                          "first_filed": max(ni["first_filed"], sh["first_filed"]), "tag": fy["tag"]}
            continue
        chain = _chain(eps_q, fy["start"], end)
        if chain and len(chain) == 3:
            eps_q[end] = {"start": chain[-1]["end"] + DAY, "end": end,
                          "val": fy["val"] - sum(c["val"] for c in chain), "derived": True,
                          "method": "Full-year EPS minus Q1-Q3 EPS (approx.)",
                          "filed": fy["filed"], "first_filed": fy["first_filed"], "tag": fy["tag"]}


# --------------------------------------------------------------------------- statement builder
def _rows(field_name: str, recs: dict, period_type: str, unit: str, cal: FiscalCalendar,
          source: Source, license_tag: LicenseTag) -> list[dict]:
    out = []
    for r in recs.values():
        fy, fq = cal.label(r["end"], period_type)
        out.append({"field": field_name, "period_end": r["end"], "period_start": r.get("start"),
                    "period_type": period_type, "fiscal_year": fy, "fiscal_quarter": fq,
                    "value": r["val"], "unit": unit, "source": source.value, "derived": r["derived"],
                    "method": r["method"],
                    "license_tag": (LicenseTag.CALCULATED_SAFE.value
                                    if r["derived"] and license_tag == LicenseTag.COMMERCIAL_OK
                                    else license_tag.value),
                    "tag": r.get("tag"), "filed": r.get("filed"), "first_filed": r.get("first_filed")})
    return out


def build_from_sec_facts(facts: dict) -> pd.DataFrame:
    """Tidy statement table (base fields only) from a companyfacts JSON."""
    periods = filing_periods(facts)
    cal = FiscalCalendar.from_filings(periods)
    accn_end = {a: pd.Timestamp(p["period_end"]) for a, p in periods.items()}
    period_ends = {pd.Timestamp(p["period_end"]) for p in periods.values()
                   if p["form"].startswith(PERIODIC_FORM_PREFIXES)}
    fy_end_set = set(cal.fy_ends)

    rows: list[dict] = []
    q_store: dict[str, dict] = {}
    fy_store: dict[str, dict] = {}
    S, LIC = Source.SEC, LicenseTag.COMMERCIAL_OK

    for name, spec in field_specs().items():
        raw = _collect(facts, spec)
        if raw.empty:
            continue
        if spec.kind == "duration":
            d = dedupe(raw[raw["start"].notna()], ["start", "end"])
            q = quarters_from_durations(d, additive=spec.special is None)
            a = annual_from_durations(d)
            q_store[name], fy_store[name] = q, a
        else:
            raw = raw.copy()
            # Cover-page (dei) values are dated on the cover; move them to the filing's period end
            is_dei = raw["tag"].str.startswith("dei:")
            raw.loc[is_dei, "end"] = raw.loc[is_dei, "accn"].map(accn_end)
            raw = raw[raw["end"].notna()]
            d = dedupe(raw, ["end"])
            d = d[d["end"].isin(period_ends)]
            recs = {r.end: {"start": None, "end": r.end, "val": r.val, "derived": False, "method": "reported",
                            "filed": r.filed, "first_filed": r.first_filed, "tag": r.tag} for r in d.itertuples()}
            q_store[name] = recs
            fy_store[name] = {e: r for e, r in recs.items() if e in fy_end_set}

    # Non-additive Q4 fills (need net income and shares first)
    if "diluted_shares" in q_store:
        _fill_weighted_shares_q4(q_store["diluted_shares"], fy_store.get("diluted_shares", {}))
    for eps_field, ratio in (("eps_diluted", True), ("eps_basic", False)):
        if eps_field in q_store:
            _fill_eps_q4(q_store[eps_field], fy_store.get(eps_field, {}), q_store.get("net_income", {}),
                         q_store.get("diluted_shares", {}), use_ratio=ratio)

    for name, spec in field_specs().items():
        if name in q_store:
            rows += _rows(name, q_store[name], "Q", spec.unit, cal, S, LIC)
            rows += _rows(name, fy_store.get(name, {}), "FY", spec.unit, cal, S, LIC)
    return pd.DataFrame(rows, columns=COLUMNS)


# --------------------------------------------------------------------------- derived lines
def wide(tidy: pd.DataFrame, period_type: str) -> pd.DataFrame:
    """period_end x field table of values."""
    t = tidy[tidy["period_type"] == period_type]
    if t.empty:
        return pd.DataFrame()
    return t.pivot_table(index="period_end", columns="field", values="value", aggfunc="first").sort_index()


def add_derived(tidy: pd.DataFrame, is_financial: bool = False) -> pd.DataFrame:
    """Append calculated lines (gross profit fallback, EBITDA, FCF, margins, growth, ratios)."""
    if tidy.empty:
        return tidy
    out = [tidy]
    for ptype in ("Q", "FY"):
        base = tidy[tidy["period_type"] == ptype]
        if base.empty:
            continue
        w = wide(tidy, ptype)
        col = lambda f: w[f] if f in w.columns else pd.Series(np.nan, index=w.index)  # noqa: E731
        meta = base.drop_duplicates("period_end").set_index("period_end")[["fiscal_year", "fiscal_quarter", "period_start"]]
        lic_by_field = base.groupby("field")["license_tag"].agg(
            lambda s: LicenseTag.DEMO_ONLY.value if (s == LicenseTag.DEMO_ONLY.value).any() else LicenseTag.CALCULATED_SAFE.value)
        src = base["source"].iloc[0]

        def emit(name: str, series: pd.Series, method: str, inputs: list[str], unit: str = "USD",
                 only_missing_of: Optional[str] = None) -> None:
            s = series.replace([np.inf, -np.inf], np.nan).dropna()
            if only_missing_of and only_missing_of in w.columns:
                s = s[w[only_missing_of].reindex(s.index).isna()]
            if s.empty:
                return
            lic = (LicenseTag.DEMO_ONLY.value
                   if any(lic_by_field.get(i) == LicenseTag.DEMO_ONLY.value for i in inputs)
                   else LicenseTag.CALCULATED_SAFE.value)
            rows = pd.DataFrame({"field": name, "period_end": s.index, "value": s.values})
            rows = rows.join(meta, on="period_end")
            rows["period_type"] = ptype
            rows["unit"] = unit
            rows["source"] = Source.CALCULATED.value if src == Source.SEC.value else src
            rows["derived"] = True
            rows["method"] = method
            rows["license_tag"] = lic
            rows["tag"] = None
            # A calculated value is known once all its inputs are known
            inp = base[base["field"].isin(inputs)].groupby("period_end")[["filed", "first_filed"]].max()
            rows = rows.join(inp, on="period_end")
            out.append(rows[COLUMNS])

        rev = col("revenue")
        if not is_financial:
            emit("gross_profit", col("revenue") - col("cost_of_revenue"), "Revenue minus cost of revenue",
                 ["revenue", "cost_of_revenue"], only_missing_of="gross_profit")
        emit("sga", col("selling_marketing") + col("general_admin"),
             "Sales & marketing + general & administrative", ["selling_marketing", "general_admin"],
             only_missing_of="sga")
        emit("total_liabilities", col("total_assets") - col("equity_incl_nci"),
             "Total assets minus equity (incl. minority interest)", ["total_assets", "equity_incl_nci"],
             only_missing_of="total_liabilities")
        gp = col("gross_profit").combine_first(col("revenue") - col("cost_of_revenue")) if not is_financial \
            else pd.Series(np.nan, index=w.index)
        ebitda = col("operating_income") + col("da")
        if not is_financial:
            emit("ebitda", ebitda, "Operating income + depreciation & amortization", ["operating_income", "da"])
        debt = col("short_term_debt").fillna(0) + col("long_term_debt").fillna(0)
        debt = debt.where(col("short_term_debt").notna() | col("long_term_debt").notna())
        emit("total_debt", debt, "Short-term debt + long-term debt", ["short_term_debt", "long_term_debt"])
        emit("net_debt", debt - col("cash").fillna(0) - col("short_term_investments").fillna(0),
             "Total debt minus cash and short-term investments",
             ["short_term_debt", "long_term_debt", "cash", "short_term_investments"])
        fcf = col("operating_cash_flow") - col("capex")
        emit("fcf", fcf, "Operating cash flow minus capex", ["operating_cash_flow", "capex"])
        sr = col("dividends_paid").fillna(0) + col("buybacks").fillna(0)
        emit("shareholder_returns", sr.where(col("dividends_paid").notna() | col("buybacks").notna()),
             "Dividends paid + share buybacks", ["dividends_paid", "buybacks"])

        pos_rev = rev.where(rev > 0)
        sga = col("sga").combine_first(col("selling_marketing") + col("general_admin"))
        ratio_specs = [("gross_margin", gp, ["gross_profit", "revenue", "cost_of_revenue"]),
                       ("operating_margin", col("operating_income"), ["operating_income", "revenue"]),
                       ("pretax_margin", col("pretax_income"), ["pretax_income", "revenue"]),
                       ("net_margin", col("net_income"), ["net_income", "revenue"]),
                       ("fcf_margin", fcf, ["operating_cash_flow", "capex", "revenue"]),
                       ("rnd_pct", col("rnd"), ["rnd", "revenue"]),
                       ("sga_pct", sga, ["sga", "selling_marketing", "general_admin", "revenue"])]
        if not is_financial:
            ratio_specs += [("ebitda_margin", ebitda, ["operating_income", "da", "revenue"]),
                            ("cogs_pct", col("cost_of_revenue"), ["cost_of_revenue", "revenue"])]
        for name, num, inputs in ratio_specs:
            emit(name, num / pos_rev, f"{field_label(name)} = value / revenue", inputs, unit="ratio")
        pretax = col("pretax_income")
        emit("effective_tax_rate", col("income_tax") / pretax.where(pretax > 0), "Income tax / pretax income",
             ["income_tax", "pretax_income"], unit="ratio")
        if not is_financial:
            emit("current_ratio", col("current_assets") / col("current_liabilities"),
                 "Current assets / current liabilities", ["current_assets", "current_liabilities"], unit="x")
        eq = col("equity")
        emit("debt_to_equity", debt / eq.where(eq > 0), "Total debt / shareholders' equity",
             ["short_term_debt", "long_term_debt", "equity"], unit="x")

        # Growth: same fiscal quarter a year earlier (YoY) and previous quarter (QoQ)
        key = meta[["fiscal_year", "fiscal_quarter"]].copy()
        key["fiscal_quarter"] = key["fiscal_quarter"].fillna(0).astype(int)  # FY rows have no quarter
        key["fiscal_year"] = key["fiscal_year"].astype(int)
        pairs = list(zip(key.index, key["fiscal_year"], key["fiscal_quarter"]))
        by_key = {(fy, fq): pe for pe, fy, fq in pairs}
        prior_year = pd.Series({pe: by_key.get((fy - 1, fq)) for pe, fy, fq in pairs}, dtype=object)

        def yoy(s: pd.Series) -> pd.Series:
            prev_vals = prior_year.map(lambda pe: s.get(pe, np.nan) if pe is not None else np.nan)
            prev_vals = prev_vals.reindex(s.index)
            return (s - prev_vals) / prev_vals.abs().where(prev_vals != 0)

        emit("revenue_yoy", yoy(rev), "Revenue vs the same period a year earlier", ["revenue"], unit="ratio")
        emit("eps_yoy", yoy(col("eps_diluted")), "Diluted EPS vs the same period a year earlier",
             ["eps_diluted"], unit="ratio")
        if ptype == "Q":
            r = rev.dropna()
            emit("revenue_qoq", r / r.shift(1) - 1, "Revenue vs the previous quarter", ["revenue"], unit="ratio")
    return pd.concat(out, ignore_index=True)


# --------------------------------------------------------------------------- TTM
NON_ADDITIVE = {"diluted_shares"}


def ttm(tidy: pd.DataFrame, field_name: str) -> Optional[dict]:
    """TTM = sum of the last 4 quarters (durations) or the latest quarter (balance sheet).
    Returns {value, as_of, derived, license_tag} or None if 4 consecutive quarters aren't available."""
    q = tidy[(tidy["field"] == field_name) & (tidy["period_type"] == "Q")].sort_values("period_end")
    if q.empty:
        return None
    spec = field_specs().get(field_name)
    lic = LicenseTag.DEMO_ONLY.value if (q["license_tag"] == LicenseTag.DEMO_ONLY.value).any() \
        else LicenseTag.CALCULATED_SAFE.value
    last = q.iloc[-1]
    if (spec and spec.kind == "instant") or field_name in {"total_debt", "net_debt"}:
        return {"value": float(last["value"]), "as_of": last["period_end"], "derived": bool(last["derived"]),
                "license_tag": last["license_tag"]}
    if field_name in NON_ADDITIVE or (spec is None and field_name in DERIVED_FIELDS
                                      and DERIVED_FIELDS[field_name][2] != "USD"):
        return None
    last4 = q.tail(4)
    if len(last4) < 4:
        return None
    span = (last4["period_end"].iloc[-1] - last4["period_end"].iloc[0]).days
    if not 250 <= span <= 290:  # 3 quarter-gaps ~ 273 days -> consecutive quarters
        return None
    return {"value": float(last4["value"].sum()), "as_of": last["period_end"], "derived": True,
            "license_tag": lic}


# --------------------------------------------------------------------------- yfinance fallback
YF_ROWS = {
    "income": {"revenue": "Total Revenue", "cost_of_revenue": "Cost Of Revenue", "gross_profit": "Gross Profit",
               "rnd": "Research And Development", "sga": "Selling General And Administration",
               "operating_income": "Operating Income", "interest_expense": "Interest Expense",
               "pretax_income": "Pretax Income", "income_tax": "Tax Provision", "net_income": "Net Income",
               "eps_basic": "Basic EPS", "eps_diluted": "Diluted EPS", "diluted_shares": "Diluted Average Shares"},
    "balance": {"total_assets": "Total Assets", "current_assets": "Current Assets",
                "cash": "Cash And Cash Equivalents", "short_term_investments": "Other Short Term Investments",
                "receivables": "Accounts Receivable", "inventory": "Inventory",
                "total_liabilities": "Total Liabilities Net Minority Interest",
                "current_liabilities": "Current Liabilities", "short_term_debt": "Current Debt",
                "long_term_debt": "Long Term Debt", "equity": "Stockholders Equity",
                "equity_incl_nci": "Total Equity Gross Minority Interest", "retained_earnings": "Retained Earnings",
                "shares_outstanding": "Ordinary Shares Number"},
    "cashflow": {"operating_cash_flow": "Operating Cash Flow", "capex": "Capital Expenditure",
                 "da": "Depreciation And Amortization", "dividends_paid": "Cash Dividends Paid",
                 "buybacks": "Repurchase Of Capital Stock"},
}
YF_NEGATED = {"capex", "dividends_paid", "buybacks"}  # yfinance reports these outflows as negatives


def build_from_yfinance(statements: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Backup builder from yfinance statement tables (DEMO_ONLY). Only ~5 quarters / 4 years."""
    annual_ends = []
    for key in ("income_a", "balance_a", "cashflow_a"):
        df = statements.get(key)
        if df is not None and not df.empty:
            annual_ends += list(pd.to_datetime(df.columns))
    cal = FiscalCalendar.from_annual_ends(sorted(set(annual_ends)))
    rows = []
    for stmt, mapping in YF_ROWS.items():
        for suffix, ptype in (("q", "Q"), ("a", "FY")):
            df = statements.get(f"{stmt}_{suffix}")
            if df is None or df.empty:
                continue
            for fname, row_name in mapping.items():
                if row_name not in df.index:
                    continue
                for col_date, val in df.loc[row_name].items():
                    if pd.isna(val):
                        continue
                    end = pd.Timestamp(col_date).normalize()
                    fy, fq = cal.label(end, ptype)
                    v = abs(float(val)) if fname in YF_NEGATED else float(val)
                    rows.append({"field": fname, "period_end": end, "period_start": None, "period_type": ptype,
                                 "fiscal_year": fy, "fiscal_quarter": fq, "value": v,
                                 "unit": field_specs()[fname].unit, "source": Source.YFINANCE.value,
                                 "derived": False, "method": "reported (yfinance)",
                                 "license_tag": LicenseTag.DEMO_ONLY.value, "tag": row_name,
                                 "filed": None, "first_filed": None})
    return pd.DataFrame(rows, columns=COLUMNS)


# --------------------------------------------------------------------------- cross-check
CROSSCHECK_FIELDS = ["revenue", "net_income", "operating_cash_flow", "total_assets"]


def cross_check(sec_tidy: pd.DataFrame, yf_tidy: pd.DataFrame, n_quarters: int = 4,
                tolerance: float = 0.02) -> pd.DataFrame:
    """Compare the last quarters of key fields between SEC and yfinance. Dates are matched
    within 10 days (yfinance labels quarters by calendar month end)."""
    out = []
    for f in CROSSCHECK_FIELDS:
        s = sec_tidy[(sec_tidy["field"] == f) & (sec_tidy["period_type"] == "Q")].sort_values("period_end").tail(n_quarters)
        y = yf_tidy[(yf_tidy["field"] == f) & (yf_tidy["period_type"] == "Q")]
        for r in s.itertuples():
            m = y[(y["period_end"] - r.period_end).abs() <= pd.Timedelta(days=10)]
            yv = float(m["value"].iloc[0]) if not m.empty else None
            diff = (r.value / yv - 1) if yv else None
            status = "No yfinance value" if yv is None else ("OK" if abs(diff) <= tolerance else "Differs > 2%")
            if status.startswith("Differs"):
                log.warning("Data quality: %s %s SEC=%.4g yfinance=%.4g (%.1f%%)",
                            f, r.period_end.date(), r.value, yv, diff * 100)
            out.append({"field": field_label(f), "period": period_label(r.fiscal_year, r.fiscal_quarter, "Q"),
                        "period_end": r.period_end.date(), "SEC EDGAR": r.value, "yfinance": yv,
                        "difference": diff, "status": status, "SEC value derived": bool(r.derived)})
    return pd.DataFrame(out)


# --------------------------------------------------------------------------- public result
@dataclass
class Financials:
    symbol: str
    source: str                      # "SEC EDGAR" or "yfinance"
    tidy: pd.DataFrame
    is_financial: bool = False
    crosscheck: Optional[pd.DataFrame] = None
    warnings: list[str] = field(default_factory=list)

    @property
    def available(self) -> bool:
        return not self.tidy.empty

    def periods(self, period_type: str, n: int) -> pd.DataFrame:
        """Last n periods (oldest -> newest): period_end, label, fiscal_year, fiscal_quarter."""
        t = self.tidy[self.tidy["period_type"] == period_type]
        if t.empty:
            return pd.DataFrame(columns=["period_end", "label", "fiscal_year", "fiscal_quarter"])
        # Use periods where revenue or net income or total assets exist (skip stray old dates)
        core = t[t["field"].isin(["revenue", "net_income", "total_assets"])]
        p = (core if not core.empty else t).drop_duplicates("period_end").sort_values("period_end").tail(n)
        p = p[["period_end", "fiscal_year", "fiscal_quarter"]].copy()
        p["label"] = [period_label(fy, fq, period_type) for fy, fq in zip(p["fiscal_year"], p["fiscal_quarter"])]
        return p.reset_index(drop=True)

    def series(self, field_name: str, period_type: str) -> pd.Series:
        t = self.tidy[(self.tidy["field"] == field_name) & (self.tidy["period_type"] == period_type)]
        return t.set_index("period_end")["value"].sort_index()

    def rows(self, field_name: str, period_type: str) -> pd.DataFrame:
        t = self.tidy[(self.tidy["field"] == field_name) & (self.tidy["period_type"] == period_type)]
        return t.set_index("period_end").sort_index()

    def license_for(self, fields: list[str]) -> LicenseTag:
        t = self.tidy[self.tidy["field"].isin(fields)]
        if t.empty:
            return LicenseTag.CALCULATED_SAFE
        if (t["license_tag"] == LicenseTag.DEMO_ONLY.value).any():
            return LicenseTag.DEMO_ONLY
        if (t["license_tag"] == LicenseTag.CALCULATED_SAFE.value).any() or (t["derived"]).any():
            return LicenseTag.CALCULATED_SAFE
        return LicenseTag.COMMERCIAL_OK

    def na_reason(self, field_name: str, since: Optional[pd.Timestamp] = None) -> Optional[str]:
        """Why a field has no data (None if it has data). With `since`, only periods from that
        date count, so an item the company stopped reporting years ago is explained too."""
        rows = self.tidy[self.tidy["field"] == field_name]
        if since is not None and not rows.empty:
            recent = rows[rows["period_end"] >= since]
            if not recent.empty:
                return None
        elif not rows.empty:
            return None
        if self.is_financial and field_name in FINANCIAL_CO_NA:
            return FINANCIAL_CO_NA[field_name]
        if not rows.empty:
            return f"Not reported since {rows['period_end'].max():%Y} (the company stopped reporting this item)"
        if field_name in ("ebitda", "ebitda_margin"):
            return "Needs operating income and depreciation & amortization, which this company doesn't report"
        if field_name in ("eps_diluted", "eps_yoy", "eps_basic"):
            return "This company doesn't report EPS in a standard form (e.g. multiple share classes)"
        return "Not reported by this company"

    def ttm(self, field_name: str) -> Optional[dict]:
        return ttm(self.tidy, field_name)
