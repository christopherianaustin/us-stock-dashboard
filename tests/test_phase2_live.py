"""Phase 2 acceptance checks against real data. Run with:  pytest -m network"""
import pytest

from core.company import resolve_ticker
from core.financials_service import load_financials

pytestmark = pytest.mark.network


def _fin(ticker, is_financial=False):
    r = resolve_ticker(ticker)
    return load_financials(r.symbol, r.cik, is_financial)


def test_aapl_last_4_quarters_match_yfinance_within_2pct():
    fin = _fin("AAPL")
    assert fin.source == "SEC EDGAR"
    check = fin.crosscheck
    for field in ("Revenue", "Net income"):
        rows = check[check["field"] == field]
        assert len(rows) == 4, f"need 4 quarters of {field}"
        assert (rows["difference"].abs() <= 0.02).all(), rows.to_string()


def test_aapl_fiscal_labels_and_q4_derived():
    fin = _fin("AAPL")
    q = fin.periods("Q", 12)
    assert len(q) == 12
    last = q.iloc[-1]
    # Apple's fiscal year ends late September -> that quarter is Q4
    if last["period_end"].month in (9, 10):
        assert last["fiscal_quarter"] == 4
        rev = fin.rows("revenue", "Q").loc[last["period_end"]]
        assert bool(rev["derived"]) and rev["method"].startswith("Full year minus")


def test_jpm_gross_profit_na_with_reason():
    fin = _fin("JPM", is_financial=True)
    assert fin.series("gross_profit", "Q").empty
    reason = fin.na_reason("gross_profit")
    assert reason and "bank" in reason.lower()
    assert not fin.series("revenue", "Q").empty


@pytest.mark.parametrize("ticker", ["MSFT", "NVDA", "KO", "TSLA"])
def test_statements_have_core_lines(ticker):
    fin = _fin(ticker)
    for f in ("revenue", "net_income", "total_assets", "operating_cash_flow", "fcf"):
        assert not fin.series(f, "Q").empty, f"{ticker} missing {f}"
    assert len(fin.periods("FY", 10)) >= 5
