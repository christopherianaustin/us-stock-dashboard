"""Phase 5 acceptance checks against real data. Run with:  pytest -m network"""
import pytest

from core.company import load_header, resolve_ticker
from core.earnings import classify
from core.earnings_service import load_earnings
from core.financials_service import load_financials

pytestmark = pytest.mark.network


def _earn(t):
    r = resolve_ticker(t)
    h = load_header(r)
    return load_earnings(r.symbol, r.cik, load_financials(r.symbol, r.cik, h.profile.is_financial_company))


def test_aapl_at_least_4_quarters_with_correct_colors():
    e = _earn("AAPL")
    h = e.history.dropna(subset=["eps_estimate", "eps_reported"])
    assert len(h) >= 4
    for _, r in h.iterrows():
        expected = "beat" if r.eps_reported > r.eps_estimate * 1.01 else (
            "miss" if r.eps_reported < r.eps_estimate * 0.99 else "inline")
        # the color class must follow the numbers (tiny rounding differences allowed at the band edge)
        assert r.result == classify(r.surprise_pct)
        if abs(r.surprise_pct) > 1.5:
            assert r.result == expected
    assert all(q.startswith("Q") for q in h["quarter"])      # labeled by fiscal quarter
    assert h["move_1d"].notna().sum() >= 4
    assert h["filing_url"].notna().all()


def test_jpm_reports_before_open():
    e = _earn("JPM")
    assert (e.history["timing"] == "before open").mean() > 0.5
