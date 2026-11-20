"""Phase 2 unit tests: Q4 derivation, YTD cash-flow fix, dedupe, fiscal labels, TTM (no internet)."""
import math

import pandas as pd
import pytest

from core.financials import (FiscalCalendar, add_derived, build_from_sec_facts, dedupe,
                             quarters_from_durations, ttm)

T = pd.Timestamp


def _d(rows):
    """rows: (start, end, val[, filed]) -> DataFrame like the builder's input."""
    recs = []
    for r in rows:
        start, end, val = r[:3]
        filed = r[3] if len(r) > 3 else end
        recs.append({"start": T(start), "end": T(end), "val": float(val), "filed": T(filed),
                     "first_filed": T(filed), "tag": "X"})
    return pd.DataFrame(recs)


# ---------- Q4 derivation ----------
def test_q4_from_full_year_minus_9m_ytd():
    d = _d([("2025-01-01", "2025-03-31", 100), ("2025-04-01", "2025-06-30", 110),
            ("2025-07-01", "2025-09-30", 120), ("2025-01-01", "2025-09-30", 330),
            ("2025-01-01", "2025-12-31", 470)])
    q = quarters_from_durations(d)
    q4 = q[T("2025-12-31")]
    assert q4["val"] == 140 and q4["derived"]
    assert q4["method"] == "Full year minus 9-month YTD"
    assert q4["start"] == T("2025-10-01")


def test_q4_from_full_year_minus_three_quarters_when_no_ytd():
    d = _d([("2025-01-01", "2025-03-31", 100), ("2025-04-01", "2025-06-30", 110),
            ("2025-07-01", "2025-09-30", 120), ("2025-01-01", "2025-12-31", 470)])
    q4 = quarters_from_durations(d)[T("2025-12-31")]
    assert q4["val"] == 140 and q4["derived"]
    assert q4["method"] == "Full year minus Q1+Q2+Q3"


def test_reported_quarters_not_derived():
    d = _d([("2025-01-01", "2025-03-31", 100)])
    q = quarters_from_durations(d)[T("2025-03-31")]
    assert q["val"] == 100 and not q["derived"]


def test_no_q4_without_enough_data():
    d = _d([("2025-01-01", "2025-03-31", 100), ("2025-01-01", "2025-12-31", 470)])
    assert T("2025-12-31") not in quarters_from_durations(d)


# ---------- YTD cash flow (10-Q reports year-to-date) ----------
def test_ytd_cash_flow_subtraction():
    # Like Apple: Q1 reported alone, Q2 and Q3 only as 6- and 9-month YTD, then full year
    d = _d([("2025-09-28", "2025-12-27", 53.925), ("2025-09-28", "2026-03-28", 82.627),
            ("2025-09-28", "2026-06-27", 116.996), ("2025-09-28", "2026-09-26", 145.097)])
    q = quarters_from_durations(d)
    assert q[T("2025-12-27")]["val"] == pytest.approx(53.925)
    assert q[T("2026-03-28")]["val"] == pytest.approx(28.702)
    assert q[T("2026-03-28")]["method"] == "YTD minus previous YTD"
    assert q[T("2026-06-27")]["val"] == pytest.approx(34.369)
    assert q[T("2026-09-26")]["val"] == pytest.approx(28.101)
    assert all(q[e]["derived"] for e in (T("2026-03-28"), T("2026-06-27"), T("2026-09-26")))


def test_eps_is_not_derived_by_subtraction():
    d = _d([("2025-01-01", "2025-03-31", 1.0), ("2025-01-01", "2025-06-30", 2.1)])
    q = quarters_from_durations(d, additive=False)
    assert list(q) == [T("2025-03-31")]


# ---------- dedupe / restatements ----------
def test_dedupe_prefers_frame_then_latest_filed_then_tag_rank():
    df = pd.DataFrame([
        {"start": T("2025-01-01"), "end": T("2025-03-31"), "val": 1.0, "filed": T("2025-05-01"), "frame": None, "rank": 0, "tag": "A"},
        {"start": T("2025-01-01"), "end": T("2025-03-31"), "val": 2.0, "filed": T("2026-05-01"), "frame": None, "rank": 0, "tag": "A"},
        {"start": T("2025-01-01"), "end": T("2025-03-31"), "val": 3.0, "filed": T("2025-08-01"), "frame": "CY2025Q1", "rank": 0, "tag": "A"},
        {"start": T("2025-01-01"), "end": T("2025-03-31"), "val": 9.0, "filed": T("2026-09-01"), "frame": "CY2025Q1", "rank": 1, "tag": "B"},
    ])
    out = dedupe(df, ["start", "end"])
    assert len(out) == 1
    assert out.iloc[0]["val"] == 3.0                     # tag rank 0 wins, then the framed fact
    assert out.iloc[0]["first_filed"] == T("2025-05-01")  # earliest time the period was public


# ---------- fiscal calendar ----------
def test_fiscal_labels_non_calendar_year():
    cal = FiscalCalendar({T("2025-09-27"): 2025, T("2026-09-26"): 2026},
                         {T("2025-12-27"): (2026, 1), T("2026-03-28"): (2026, 2)})
    assert cal.label(T("2025-12-27"), "Q") == (2026, 1)
    assert cal.label(T("2026-09-26"), "Q") == (2026, 4)
    assert cal.label(T("2026-09-26"), "FY") == (2026, None)
    assert cal.label(T("2026-06-27"), "Q") == (2026, 3)       # estimated from the year end
    assert cal.label(T("2026-12-26"), "Q") == (2027, 1)       # after the last known year end


# ---------- end-to-end on a tiny fake companyfacts ----------
def _fact(start, end, val, fy, fp, form, filed, accn, frame=None):
    r = {"end": end, "val": val, "fy": fy, "fp": fp, "form": form, "filed": filed, "accn": accn}
    if start:
        r["start"] = start
    if frame:
        r["frame"] = frame
    return r


def _fake_facts():
    q1 = ("A1", "2025-04-30", 2025, "Q1", "10-Q")
    q2 = ("A2", "2025-07-30", 2025, "Q2", "10-Q")
    q3 = ("A3", "2025-10-30", 2025, "Q3", "10-Q")
    k = ("A4", "2026-02-15", 2025, "FY", "10-K")

    def f(meta, start, end, val):
        accn, filed, fy, fp, form = meta
        return _fact(start, end, val, fy, fp, form, filed, accn)

    revenue = [f(q1, "2025-01-01", "2025-03-31", 100), f(q2, "2025-04-01", "2025-06-30", 110),
               f(q3, "2025-07-01", "2025-09-30", 120), f(k, "2025-01-01", "2025-12-31", 470)]
    ni = [f(q1, "2025-01-01", "2025-03-31", 10), f(q2, "2025-04-01", "2025-06-30", 11),
          f(q3, "2025-07-01", "2025-09-30", 12), f(k, "2025-01-01", "2025-12-31", 49)]
    shares = [f(q1, "2025-01-01", "2025-03-31", 10), f(q2, "2025-04-01", "2025-06-30", 10),
              f(q3, "2025-07-01", "2025-09-30", 10), f(k, "2025-01-01", "2025-12-31", 10)]
    eps = [f(q1, "2025-01-01", "2025-03-31", 1.0), f(q2, "2025-04-01", "2025-06-30", 1.1),
           f(q3, "2025-07-01", "2025-09-30", 1.2), f(k, "2025-01-01", "2025-12-31", 4.9)]
    ocf = [f(q1, "2025-01-01", "2025-03-31", 20), f(q2, "2025-01-01", "2025-06-30", 45),
           f(q3, "2025-01-01", "2025-09-30", 75), f(k, "2025-01-01", "2025-12-31", 110)]
    capex = [f(q1, "2025-01-01", "2025-03-31", 5), f(q2, "2025-01-01", "2025-06-30", 10),
             f(q3, "2025-01-01", "2025-09-30", 15), f(k, "2025-01-01", "2025-12-31", 20)]
    assets = [f(q1, None, "2025-03-31", 1000), f(q2, None, "2025-06-30", 1010),
              f(q3, None, "2025-09-30", 1020), f(k, None, "2025-12-31", 1030)]
    return {"facts": {"us-gaap": {
        "Revenues": {"units": {"USD": revenue}},
        "NetIncomeLoss": {"units": {"USD": ni}},
        "WeightedAverageNumberOfDilutedSharesOutstanding": {"units": {"shares": shares}},
        "EarningsPerShareDiluted": {"units": {"USD/shares": eps}},
        "NetCashProvidedByUsedInOperatingActivities": {"units": {"USD": ocf}},
        "PaymentsToAcquirePropertyPlantAndEquipment": {"units": {"USD": capex}},
        "Assets": {"units": {"USD": assets}},
    }}}


def test_build_end_to_end():
    tidy = add_derived(build_from_sec_facts(_fake_facts()))
    get = lambda f, e, pt="Q": tidy[(tidy.field == f) & (tidy.period_end == T(e)) & (tidy.period_type == pt)].iloc[0]  # noqa: E731

    q4_rev = get("revenue", "2025-12-31")
    assert q4_rev.value == 140 and q4_rev.derived and q4_rev.fiscal_quarter == 4 and q4_rev.fiscal_year == 2025
    assert q4_rev.license_tag == "CALCULATED_SAFE"
    assert get("revenue", "2025-03-31").license_tag == "COMMERCIAL_OK"

    # EPS Q4 = Q4 net income / Q4 diluted shares = 16 / 10
    q4_eps = get("eps_diluted", "2025-12-31")
    assert q4_eps.value == pytest.approx(1.6) and q4_eps.method.startswith("Q4 net income")

    # Cash flow YTD fix: Q2 = 45-20, Q3 = 75-45, Q4 = 110-75
    assert [get("operating_cash_flow", e).value for e in ("2025-06-30", "2025-09-30", "2025-12-31")] == [25, 30, 35]
    # FCF = OCF - capex per quarter: Q2 = 25 - 5
    assert get("fcf", "2025-06-30").value == 20
    # Margins
    assert get("net_margin", "2025-03-31").value == pytest.approx(0.10)
    # Annual
    assert get("revenue", "2025-12-31", "FY").value == 470
    # Balance sheet instants
    assert get("total_assets", "2025-09-30").value == 1020

    ttm_rev = ttm(tidy, "revenue")
    assert ttm_rev["value"] == 470 and ttm_rev["license_tag"] == "CALCULATED_SAFE"
    assert ttm(tidy, "total_assets")["value"] == 1030


def test_financial_company_has_no_gross_profit_or_ebitda():
    tidy = add_derived(build_from_sec_facts(_fake_facts()), is_financial=True)
    assert tidy[tidy.field.isin(["gross_profit", "ebitda", "gross_margin"])].empty
