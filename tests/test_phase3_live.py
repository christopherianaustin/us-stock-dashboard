"""Phase 3 acceptance checks against real data. Run with:  pytest -m network"""
import pytest

from core.analysis import load_analysis
from core.company import load_header, resolve_ticker
from core.financials_service import load_financials

pytestmark = pytest.mark.network


def _analysis(ticker):
    r = resolve_ticker(ticker)
    h = load_header(r)
    fin = load_financials(r.symbol, r.cik, h.profile.is_financial_company)
    return load_analysis(r.symbol, h, fin)


def test_aapl_ratios_close_to_yahoo():
    a = _analysis("AAPL")
    yc = a.yahoo_compare.set_index("metric")
    # Same-definition ratios should be within 10% (timing of the latest quarter can differ slightly)
    for m in ("pe", "ps", "pb", "ev_ebitda", "roe", "net_margin", "current_ratio"):
        diff = yc.loc[m, "difference"]
        assert diff is not None and abs(diff) <= 0.10, f"{m}: ours {yc.loc[m, 'ours']} vs yahoo {yc.loc[m, 'yahoo']}"


def test_aapl_history_and_scores():
    a = _analysis("AAPL")
    assert a.stats["pe"].days > 1000 and a.stats["pe"].median > 0
    assert a.piotroski.tested == 9
    assert a.altman.z is not None and a.graham.available


def test_negative_eps_shows_na_pe():
    a = _analysis("PLUG")  # unprofitable small cap
    assert not a.snapshot["pe"].available
    assert a.snapshot["pe"].na_reason == "N/A (negative earnings)"


def test_bank_ratios_na():
    a = _analysis("JPM")
    assert a.snapshot["roe"].available and a.snapshot["pe"].available
    assert not a.snapshot["ev_ebitda"].available and a.altman.z is None
