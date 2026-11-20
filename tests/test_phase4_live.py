"""Phase 4 acceptance checks against real data. Run with:  pytest -m network"""
import pytest

from core.price_service import load_price_analysis

pytestmark = pytest.mark.network


@pytest.mark.parametrize("ticker,sector", [("AAPL", "Technology"), ("TSLA", "Consumer Cyclical")])
def test_support_resistance_sensible(ticker, sector):
    p = load_price_analysis(ticker, sector)
    price = p.snap.price
    sr = p.sr["1y"]
    assert sr.supports or sr.resistances
    for lvl in sr.supports:
        assert lvl.price < price and -0.5 < lvl.distance < 0 and lvl.touches >= 1
    for lvl in sr.resistances:
        assert lvl.price > price and 0 < lvl.distance < 1.0
    # levels must sit inside the 1-year trading range
    low, high = p.df.tail(252)["Low"].min(), p.df.tail(252)["High"].max()
    for lvl in sr.supports + sr.resistances:
        assert low - 1e-6 <= lvl.price <= high + 1e-6


def test_indicators_and_risk_present():
    p = load_price_analysis("AAPL", "Technology")
    s = p.snap
    assert 0 <= s.rsi14 <= 100 and s.sma200 > 0 and s.atr14 > 0
    assert p.pivots and p.pivots["S1"] < p.pivots["P"] < p.pivots["R1"]
    assert 0.3 < p.risk.beta < 2.5 and 0.05 < p.risk.volatility_1y < 1.0
    assert p.risk.max_drawdown_5y <= p.risk.max_drawdown_1y <= 0
    assert "SPY" in p.benchmarks and p.sector_etf == "XLK"
    assert p.returns.loc["5Y", "AAPL"] is not None
