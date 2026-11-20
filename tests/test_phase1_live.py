"""Phase 1 live checks against real data sources.
Run with:  pytest -m network
"""
import pytest

from core.company import TickerNotFound, load_header, resolve_ticker

pytestmark = pytest.mark.network


@pytest.mark.parametrize("ticker", ["AAPL", "JPM", "BRK-B", "MSFT", "NVDA", "KO", "TSLA"])
def test_header_loads(ticker):
    resolved = resolve_ticker(ticker)
    assert resolved.cik, "should be found in the SEC ticker list"
    h = load_header(resolved)
    assert h.profile.name.available
    assert h.price.available and h.price.value > 0
    assert h.market_cap.available and h.market_cap.value > 1e9
    assert h.week52_low.value <= h.week52_high.value
    assert h.data_freshness.available


def test_brk_normalized():
    assert resolve_ticker("brk-b").symbol == "BRK.B"
    assert resolve_ticker("BRK.B").cik == "0001067983"


def test_jpm_is_financial():
    h = load_header(resolve_ticker("JPM"))
    assert h.profile.is_financial_company


@pytest.mark.parametrize("bad", ["ZZZZQ", "NOTATICKER1", "!!!"])
def test_invalid_ticker_friendly(bad):
    with pytest.raises(TickerNotFound) as exc:
        resolve_ticker(bad)
    assert "ticker" in str(exc.value).lower()
