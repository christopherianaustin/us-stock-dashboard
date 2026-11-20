"""Phase 6 acceptance checks against real data. Run with:  pytest -m network"""
import pytest

from core.company import load_header, resolve_ticker
from core.extras_service import load_dividends, load_news, load_ownership
from core.financials_service import load_financials
from core.ratios import quarterly_metrics

pytestmark = pytest.mark.network


def _div(t):
    r = resolve_ticker(t)
    h = load_header(r)
    fin = load_financials(r.symbol, r.cik, h.profile.is_financial_company)
    return load_dividends(r.symbol, h.price.value, fin, quarterly_metrics(fin))


def test_ko_full_history_and_streak():
    d = _div("KO")
    assert d.summary.pays
    assert d.dividends.index.min().year <= 1965          # full history back to the 1960s
    assert d.summary.streak >= 60                        # raised every year for 60+ years
    assert 0.01 < d.summary.yield_ttm < 0.06 and d.summary.frequency == 4
    assert 0.3 < d.payout_ratio < 1.2


def test_tsla_no_dividend():
    d = _div("TSLA")
    assert not d.summary.pays and d.summary.reason == "This company does not pay a dividend."


def test_ownership_and_news():
    o = load_ownership("KO")
    assert o.breakdown and not o.top_institutions.empty and not o.recommendations.empty
    n = load_news("KO", "0000021344")
    assert n.items and n.filings
    assert any(f.form == "10-Q" for f in n.filings)
