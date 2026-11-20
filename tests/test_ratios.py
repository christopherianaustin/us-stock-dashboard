"""Phase 3 unit tests: every formula with small hand-made examples (no internet)."""
import math

import numpy as np
import pandas as pd
import pytest

from core.financials import Financials, add_derived
from core.models import LicenseTag
from core.quality_scores import altman_z, altman_zone, piotroski
from core.ratios import (EstimateInputs, MarketInputs, cagr, compute_snapshot, dupont, effective_tax_rate,
                         enterprise_value, graham_number, pe_ratio, positive_div, quarterly_metrics, roic, safe_div,
                         split_adjust, split_factor_after)
from core.valuation import (dcf, dcf_default_growth, dcf_scenarios, history_stats, peer_medians, peer_row,
                            percentile_sentence, valuation_history)

T = pd.Timestamp


# ---------------------------------------------------------------- basic formulas
def test_safe_div():
    assert safe_div(10, 4) == 2.5
    assert safe_div(1, 0) is None and safe_div(None, 2) is None and safe_div(1, float("nan")) is None


def test_cagr():
    assert cagr(100, 121, 2) == pytest.approx(0.10)
    assert cagr(100, 100 * 1.05 ** 5, 5) == pytest.approx(0.05)
    assert cagr(-5, 10, 3) is None and cagr(5, -10, 3) is None and cagr(0, 10, 3) is None


def test_pe_ratio_and_negative_earnings():
    assert pe_ratio(100, 5) == (20.0, None)
    v, reason = pe_ratio(100, -2)
    assert v is None and reason == "N/A (negative earnings)"
    assert pe_ratio(100, 0)[0] is None


def test_positive_div():
    assert positive_div(50, 10, "x") == (5.0, None)
    assert positive_div(50, -10, "negative") == (None, "negative")


def test_enterprise_value():
    assert enterprise_value(1000, 200, 50) == 1150
    assert enterprise_value(1000, None, None) == 1000
    assert enterprise_value(None, 200, 50) is None


def test_graham_number():
    v, _ = graham_number(4, 10)
    assert v == pytest.approx(math.sqrt(22.5 * 4 * 10))  # = 30
    assert graham_number(-1, 10)[0] is None and graham_number(4, -1)[0] is None


def test_effective_tax_rate():
    assert effective_tax_rate(20, 100) == pytest.approx(0.20)
    assert effective_tax_rate(20, -100) == 0.21      # loss -> default rate
    assert effective_tax_rate(80, 100) == 0.5        # capped


def test_roic():
    # NOPAT = 100 x (1 - 0.2) = 80; invested = 300 + 500 - 100 = 700
    assert roic(100, 0.2, 300, 500, 100) == pytest.approx(80 / 700)
    assert roic(100, 0.2, 0, 100, 500) is None       # negative invested capital


def test_dupont_multiplies_back_to_roe():
    d = dupont(net_income=20, revenue=200, avg_assets=400, avg_equity=100)
    assert d["net_margin"] == pytest.approx(0.10)
    assert d["asset_turnover"] == pytest.approx(0.5)
    assert d["equity_multiplier"] == pytest.approx(4.0)
    assert d["roe"] == pytest.approx(20 / 100)


# ---------------------------------------------------------------- splits
def test_split_adjustment():
    splits = pd.Series([10.0], index=[T("2024-06-10")])
    assert split_factor_after(T("2024-01-01"), splits) == 10
    assert split_factor_after(T("2024-07-01"), splits) == 1
    eps = pd.Series([5.0, 0.6], index=[T("2023-12-31"), T("2024-06-30")])
    filed = pd.Series([T("2024-02-20"), T("2024-08-20")], index=eps.index)
    adj = split_adjust(eps, filed, splits, per_share=True)
    assert list(adj) == [0.5, 0.6]                   # old EPS divided by 10, new one unchanged
    sh = split_adjust(pd.Series([100.0], index=[T("2023-12-31")]), filed.iloc[:1], splits, per_share=False)
    assert sh.iloc[0] == 1000


# ---------------------------------------------------------------- quarterly table + snapshot
def _fake_fin(is_financial=False, ni=25.0):
    """8 straight quarters with simple, round numbers."""
    ends = pd.date_range("2024-03-31", periods=8, freq="QE")
    rows = []

    def add(field, val, unit="USD"):
        for i, e in enumerate(ends):
            v = val(i) if callable(val) else val
            rows.append({"field": field, "period_end": e, "period_start": e - pd.Timedelta(days=90),
                         "period_type": "Q", "fiscal_year": e.year, "fiscal_quarter": (e.month - 1) // 3 + 1,
                         "value": v, "unit": unit, "source": "SEC EDGAR", "derived": False, "method": "reported",
                         "license_tag": "COMMERCIAL_OK", "tag": "X", "filed": e + pd.Timedelta(days=30),
                         "first_filed": e + pd.Timedelta(days=30)})

    add("revenue", 100.0)
    add("net_income", ni)
    add("operating_income", 30.0)
    add("da", 5.0)
    add("income_tax", 5.0)
    add("pretax_income", 25.0)
    add("interest_expense", 2.0)
    add("operating_cash_flow", 35.0)
    add("capex", 10.0)
    add("eps_diluted", ni / 10, "USD/shares")
    add("diluted_shares", 10.0, "shares")
    add("total_assets", 1000.0)
    add("equity", 400.0)
    add("long_term_debt", 200.0)
    add("cash", 50.0)
    add("current_assets", 300.0)
    add("current_liabilities", 150.0)
    add("inventory", 30.0)
    add("retained_earnings", 250.0)
    add("total_liabilities", 600.0)
    tidy = add_derived(pd.DataFrame(rows), is_financial)
    return Financials(symbol="TEST", source="SEC EDGAR", tidy=tidy, is_financial=is_financial)


def test_quarterly_metrics_ttm_and_ratios():
    q = quarterly_metrics(_fake_fin())
    last = q.iloc[-1]
    assert last["revenue_ttm"] == 400 and last["net_income_ttm"] == 100
    assert last["ebitda_ttm"] == 140 and last["fcf_ttm"] == 100
    assert last["avg_equity"] == 400 and last["roe"] == pytest.approx(0.25)
    assert last["roa"] == pytest.approx(0.10)
    assert last["current_ratio"] == 2.0
    assert last["quick_ratio"] == pytest.approx(270 / 150)
    assert last["debt_to_equity"] == pytest.approx(0.5)
    assert last["debt_to_ebitda"] == pytest.approx(200 / 140)
    assert last["interest_coverage"] == pytest.approx(120 / 8)
    assert last["cash_conversion"] == pytest.approx(140 / 100)
    assert last["net_debt"] == 150
    assert last["bvps"] == 40
    # ROIC = 120 x (1 - 20/100) / (200 + 400 - 50)
    assert last["roic"] == pytest.approx(96 / 550)
    # First 3 rows have no full TTM
    assert q["revenue_ttm"].iloc[:3].isna().all()


def test_snapshot_valuation_and_licenses():
    fin = _fake_fin()
    q = quarterly_metrics(fin)
    snap = compute_snapshot(fin, q, MarketInputs(price=50.0, market_cap=500.0, price_license=LicenseTag.DEMO_ONLY),
                            EstimateInputs(forward_eps=12.5, growth=0.10, target_mean=60.0))
    assert snap["pe"].value == pytest.approx(50 / 10)           # TTM EPS = 4 x 2.5
    assert snap["forward_pe"].value == pytest.approx(4.0)
    assert snap["peg"].value == pytest.approx(5 / 10)
    assert snap["ps"].value == pytest.approx(500 / 400)
    assert snap["pb"].value == pytest.approx(500 / 400)
    assert snap["enterprise_value"].value == 650
    assert snap["ev_ebitda"].value == pytest.approx(650 / 140)
    assert snap["ev_revenue"].value == pytest.approx(650 / 400)
    assert snap["p_fcf"].value == pytest.approx(5.0)
    assert snap["fcf_yield"].value == pytest.approx(0.2)
    assert snap["earnings_yield"].value == pytest.approx(0.2)
    assert snap["target_upside"].value == pytest.approx(0.2)
    # Price-based ratios inherit the demo license of the price; SEC-only ratios are "calculated safe"
    assert snap["pe"].license_tag == LicenseTag.DEMO_ONLY
    assert snap["roe"].license_tag == LicenseTag.CALCULATED_SAFE


def test_negative_eps_gives_na_pe():
    fin = _fake_fin(ni=-10.0)
    q = quarterly_metrics(fin)
    snap = compute_snapshot(fin, q, MarketInputs(price=50.0, market_cap=500.0), EstimateInputs())
    assert not snap["pe"].available
    assert snap["pe"].na_reason == "N/A (negative earnings)"
    assert snap["earnings_yield"].value < 0


def test_bank_ratios_na_with_reason():
    fin = _fake_fin(is_financial=True)
    q = quarterly_metrics(fin)
    snap = compute_snapshot(fin, q, MarketInputs(price=50.0, market_cap=500.0), EstimateInputs())
    for k in ("ev_ebitda", "roic", "interest_coverage", "current_ratio"):
        assert not snap[k].available and "bank" in snap[k].na_reason.lower()
    assert snap["roe"].available


# ---------------------------------------------------------------- valuation history
def test_valuation_history_uses_only_known_data():
    q = pd.DataFrame({
        "known_date": [T("2024-02-01"), T("2024-05-01")],
        "eps_diluted_ttm": [2.0, 4.0], "revenue_ttm": [100.0, 100.0], "ebitda_ttm": [50.0, 50.0],
        "net_income_ttm": [20.0, 40.0], "net_debt": [0.0, 0.0], "shares": [10.0, 10.0],
    }, index=[T("2023-12-31"), T("2024-03-31")])
    close = pd.Series(40.0, index=pd.date_range("2024-03-01", "2024-06-01", freq="D"))
    h = valuation_history(q, close)
    assert h.loc[T("2024-04-30"), "pe"] == 20   # Q1 results not public yet -> old EPS 2.0
    assert h.loc[T("2024-05-01"), "pe"] == 10   # filed that day -> new EPS 4.0
    assert h.loc[T("2024-05-15"), "ps"] == pytest.approx(400 / 100)


def test_history_stats_and_sentence():
    s = pd.Series(range(1, 101), dtype=float)
    st = history_stats(s, current=90.5)
    assert st.median == pytest.approx(50.5) and st.low == 1 and st.high == 100
    assert st.percentile == pytest.approx(0.90)
    assert "higher than 90%" in percentile_sentence("P/E", st)
    assert "lower than" in percentile_sentence("P/E", history_stats(s, current=10.5))


# ---------------------------------------------------------------- DCF
def test_dcf_by_hand():
    # FCF 100, no growth, r = 10%, tg = 0 -> value of a perpetuity = 100 / 0.10 = 1000
    r = dcf(100, 0.0, 0.10, 0.0, net_debt=0, shares=10)
    assert r.enterprise_value == pytest.approx(1000)
    assert r.per_share == pytest.approx(100)
    r2 = dcf(100, 0.0, 0.10, 0.0, net_debt=200, shares=10)
    assert r2.per_share == pytest.approx(80)


def test_dcf_invalid_inputs():
    assert dcf(-5, 0.05, 0.1, 0.02, 0, 10).reason == "A DCF needs positive free cash flow"
    assert dcf(100, 0.05, 0.02, 0.03, 0, 10).per_share is None


def test_dcf_scenarios_ordered():
    sc = dcf_scenarios(100, 0.10, 0.10, 0.025, 0, 10)
    assert sc["Bear"].per_share < sc["Base"].per_share < sc["Bull"].per_share


def test_dcf_default_growth_capped():
    assert dcf_default_growth(0.35, None)[0] == 0.20
    assert dcf_default_growth(None, 0.08)[0] == 0.08
    assert dcf_default_growth(None, -0.5)[0] == -0.10
    assert dcf_default_growth(None, None)[0] == 0.05


# ---------------------------------------------------------------- peers
def test_peer_row_and_median():
    r = peer_row("XYZ", {"shortName": "Xyz", "marketCap": 1e9, "trailingPE": -5, "priceToSalesTrailing12Months": 2,
                         "trailingEps": -1})
    assert r["pe"] is None and r["pe_note"] == "negative earnings" and r["ps"] == 2
    med = peer_medians(pd.DataFrame([{"pe": 10.0, "ps": 1.0}, {"pe": 20.0, "ps": 3.0}, {"pe": None, "ps": 2.0}]))
    assert med["pe"] == 15 and med["ps"] == 2


# ---------------------------------------------------------------- quality scores
def test_altman_zone_boundaries():
    assert altman_zone(3.5) == "Safe" and altman_zone(2.5) == "Grey" and altman_zone(1.0) == "Distress"


def test_altman_by_hand():
    q = pd.DataFrame([{"total_assets": 1000.0, "current_assets": 300.0, "current_liabilities": 150.0,
                       "retained_earnings": 250.0, "operating_income_ttm": 120.0, "total_liabilities": 600.0,
                       "revenue_ttm": 400.0}])
    r = altman_z(q, market_cap=500.0, is_financial=False)
    expected = 1.2 * 0.15 + 1.4 * 0.25 + 3.3 * 0.12 + 0.6 * (500 / 600) + 1.0 * 0.4
    assert r.z == pytest.approx(expected)
    assert altman_z(q, 500.0, is_financial=True).z is None


def _annual_fin(years: dict):
    rows = []
    for fy, vals in years.items():
        end = T(f"{fy}-12-31")
        for f, v in vals.items():
            rows.append({"field": f, "period_end": end, "period_start": end - pd.Timedelta(days=364),
                         "period_type": "FY", "fiscal_year": fy, "fiscal_quarter": None, "value": v,
                         "unit": "USD", "source": "SEC EDGAR", "derived": False, "method": "reported",
                         "license_tag": "COMMERCIAL_OK", "tag": "X", "filed": end, "first_filed": end})
    return Financials(symbol="T", source="SEC EDGAR", tidy=pd.DataFrame(rows))


def test_piotroski_perfect_and_weak():
    base = {"total_assets": 1000, "net_income": 50, "operating_cash_flow": 60, "long_term_debt": 300,
            "current_assets": 300, "current_liabilities": 200, "diluted_shares": 100, "revenue": 800,
            "gross_profit": 300}
    better = {**base, "net_income": 80, "operating_cash_flow": 100, "long_term_debt": 200, "current_assets": 400,
              "diluted_shares": 95, "revenue": 1000, "gross_profit": 420}
    good = piotroski(_annual_fin({2023: base, 2024: base, 2025: better}))
    assert good.tested == 9 and good.score == 9
    worse = {**base, "net_income": -20, "operating_cash_flow": -30, "long_term_debt": 500, "current_assets": 200,
             "diluted_shares": 120, "revenue": 700, "gross_profit": 200}
    bad = piotroski(_annual_fin({2023: base, 2024: base, 2025: worse}))
    assert bad.score == 0
    assert piotroski(_annual_fin({2025: base})).reason
