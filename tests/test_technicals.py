"""Phase 4 unit tests on synthetic price series (no internet): SMA, EMA, RSI, MACD, Bollinger,
ATR, support/resistance, pivots, signals and risk metrics."""
import numpy as np
import pandas as pd
import pytest

from core.risk import (beta, drawdown_series, max_drawdown, monthly_returns, period_return, rebased,
                       returns_table, sharpe, volatility)
from core.technicals import (add_indicators, atr, bollinger, ema, macd, rsi, sma, support_resistance,
                             swing_points, trend_signals, weekly_pivots)


def _bars(close, spread=1.0, volume=1_000_000):
    idx = pd.bdate_range("2024-01-01", periods=len(close))
    c = pd.Series(close, index=idx, dtype=float)
    return pd.DataFrame({"Open": c, "High": c + spread, "Low": c - spread, "Close": c,
                         "Volume": float(volume)}, index=idx)


# ---------------------------------------------------------------- moving averages
def test_sma_by_hand():
    s = pd.Series([1, 2, 3, 4, 5], dtype=float)
    out = sma(s, 3)
    assert out.isna().sum() == 2 and list(out[2:]) == [2, 3, 4]


def test_ema_constant_series_is_constant():
    s = pd.Series([10.0] * 30)
    assert ema(s, 12).dropna().eq(10).all()


def test_ema_reacts_faster_than_sma():
    s = pd.Series([10.0] * 30 + [20.0] * 5)
    assert ema(s, 10).iloc[-1] > sma(s, 10).iloc[-1]


# ---------------------------------------------------------------- RSI
def test_rsi_only_gains_is_100_only_losses_is_0():
    up = pd.Series(np.arange(1, 41, dtype=float))
    down = pd.Series(np.arange(40, 0, -1, dtype=float))
    assert rsi(up).iloc[-1] == pytest.approx(100)
    assert rsi(down).iloc[-1] == pytest.approx(0)


def test_rsi_balanced_moves_is_50():
    s = pd.Series([10.0, 11.0] * 40)  # equal gains and losses
    assert rsi(s).iloc[-1] == pytest.approx(50, abs=3)


def test_rsi_wilder_first_value_by_hand():
    # 14 changes: 7 gains of +1 and 7 losses of -1 after the first value -> RS = 1 -> RSI 50
    s = pd.Series([10, 11, 10, 11, 10, 11, 10, 11, 10, 11, 10, 11, 10, 11, 10], dtype=float)
    r = rsi(s, 14)
    assert r.iloc[:14].isna().all()
    assert r.iloc[14] == pytest.approx(50)
    # next bar: +1 gain -> avg gain = (0.5 x 13 + 1) / 14, avg loss = 0.5 x 13 / 14
    s2 = pd.concat([s, pd.Series([11.0])], ignore_index=True)
    g, l = (0.5 * 13 + 1) / 14, 0.5 * 13 / 14
    assert rsi(s2, 14).iloc[15] == pytest.approx(100 - 100 / (1 + g / l))


def test_rsi_bounds():
    rng = np.random.default_rng(0)
    s = pd.Series(100 + rng.normal(0, 1, 300).cumsum())
    r = rsi(s).dropna()
    assert ((r >= 0) & (r <= 100)).all()


# ---------------------------------------------------------------- MACD
def test_macd_definition():
    rng = np.random.default_rng(1)
    s = pd.Series(100 + rng.normal(0, 1, 200).cumsum())
    m = macd(s)
    expected = s.ewm(span=12, adjust=False).mean() - s.ewm(span=26, adjust=False).mean()
    assert m["macd"].iloc[-1] == pytest.approx(expected.iloc[-1])
    assert m["hist"].iloc[-1] == pytest.approx(m["macd"].iloc[-1] - m["signal"].iloc[-1])
    assert m["macd"].iloc[:25].isna().all()


def test_macd_positive_in_uptrend():
    s = pd.Series(np.linspace(100, 200, 120))
    assert macd(s)["macd"].iloc[-1] > 0


# ---------------------------------------------------------------- Bollinger / ATR
def test_bollinger_constant_series_has_no_width():
    b = bollinger(pd.Series([50.0] * 25))
    assert b["bb_upper"].iloc[-1] == b["bb_lower"].iloc[-1] == 50


def test_atr_constant_range():
    df = _bars([100.0] * 40, spread=2.0)  # high-low = 4 every day, no gaps
    assert atr(df["High"], df["Low"], df["Close"]).iloc[-1] == pytest.approx(4.0)


# ---------------------------------------------------------------- support / resistance
def _range_bound(n=260):
    """Price swinging between ~90 and ~110 (clear support 90, resistance 110), ending at 100."""
    t = np.arange(n)
    close = 100 + 10 * np.sin(2 * np.pi * t / 40)
    close[-1] = 100.0
    return add_indicators(_bars(close, spread=0.5))


def test_swing_points_found():
    pts = swing_points(_range_bound(), 5)
    assert (pts["type"] == "high").sum() >= 5 and (pts["type"] == "low").sum() >= 5


def test_support_resistance_on_range():
    df = _range_bound()
    sr = support_resistance(df, "1y")
    assert sr.nearest_support is not None and sr.nearest_resistance is not None
    assert sr.nearest_support.price == pytest.approx(89.5, abs=1.5)      # lows ~ 90 - spread
    assert sr.nearest_resistance.price == pytest.approx(110.5, abs=1.5)
    assert sr.nearest_support.touches >= 5
    assert sr.nearest_support.distance < 0 < sr.nearest_resistance.distance
    assert len(sr.supports) <= 3 and len(sr.resistances) <= 3


def test_support_resistance_clustering_merges_close_levels():
    df = _range_bound()
    sr = support_resistance(df, "1y")
    # all lows are within the tolerance, so they must form ONE support level
    assert len(sr.supports) == 1


def test_sr_recent_touches_weigh_more():
    df = _range_bound()
    sr = support_resistance(df, "1y")
    assert sr.nearest_support.strength > sr.nearest_support.touches  # recency weights > 1


# ---------------------------------------------------------------- pivots
def test_weekly_pivots_by_hand():
    idx = pd.bdate_range("2024-01-01", "2024-01-10")  # Mon 1st .. Wed 10th (2nd week incomplete)
    c = pd.Series([10, 11, 12, 11, 10, 10, 10, 10], index=idx, dtype=float)
    df = pd.DataFrame({"High": c + 1, "Low": c - 1, "Close": c}, index=idx)
    p = weekly_pivots(df)
    # previous complete week: H = 13, L = 9, C = 10 -> P = 32/3
    assert p["week_ending"] == pd.Timestamp("2024-01-05")
    assert p["P"] == pytest.approx(32 / 3)
    assert p["R1"] == pytest.approx(2 * 32 / 3 - 9)
    assert p["S1"] == pytest.approx(2 * 32 / 3 - 13)
    assert p["R2"] == pytest.approx(32 / 3 + 4) and p["S2"] == pytest.approx(32 / 3 - 4)


# ---------------------------------------------------------------- signals
def test_golden_cross_detected():
    # long decline then strong rise -> SMA50 crosses above SMA200 near the end
    close = np.concatenate([np.linspace(200, 100, 250), np.linspace(100, 260, 120)])
    df = add_indicators(_bars(close))
    sig = {s.name: s for s in trend_signals(df, lookback=400)}
    assert "Golden cross" in sig and sig["Golden cross"].date is not None
    assert "above its 200-day" in sig["Price vs 200-day average"].fact


def test_rsi_overbought_signal_is_a_fact_not_advice():
    df = add_indicators(_bars(np.linspace(100, 300, 260)))
    texts = " ".join(s.fact for s in trend_signals(df)).lower()
    assert "overbought zone" in texts
    assert "buy" not in texts.replace("overbought", "") and "sell" not in texts


# ---------------------------------------------------------------- risk
def _daily(values, start="2020-01-01"):
    return pd.Series(values, index=pd.bdate_range(start, periods=len(values)), dtype=float)


def test_period_returns():
    s = _daily(np.linspace(100, 200, 1400))
    assert period_return(s, "1D") == pytest.approx(s.iloc[-1] / s.iloc[-2] - 1)
    assert period_return(s, "5Y") is not None
    assert period_return(_daily([1.0, 2.0, 3.0]), "1Y") is None   # history too short
    t = returns_table({"A": s, "B": s})
    assert list(t.columns) == ["A", "B"] and "YTD" in t.index


def test_beta_of_scaled_series():
    rng = np.random.default_rng(2)
    m = _daily(100 * np.exp(np.cumsum(rng.normal(0, 0.01, 800))))
    r = m.pct_change().fillna(0)
    s = 100 * (1 + 2 * r).cumprod()      # returns exactly 2x the market every day
    assert beta(s, m) == pytest.approx(2.0, rel=0.15)


def test_volatility_and_drawdown():
    s = _daily([100, 120, 90, 95, 130] * 60)
    assert volatility(s) > 0
    dd = drawdown_series(_daily([100, 120, 90, 130]))
    assert dd.min() == pytest.approx(90 / 120 - 1)
    assert max_drawdown(_daily([100, 120, 90, 130])) == pytest.approx(-0.25)


def test_sharpe_positive_for_steady_gain():
    rng = np.random.default_rng(3)
    s = _daily(100 * np.exp(np.cumsum(0.001 + rng.normal(0, 0.005, 400))))
    assert sharpe(s, 0.02) > 0


def test_monthly_returns_shape_and_rebase():
    s = _daily(np.linspace(100, 130, 520))
    m = monthly_returns(s)
    assert list(m.columns)[:3] == ["Jan", "Feb", "Mar"] and (m.stack().dropna() > 0).all()
    rb = rebased({"a": s, "b": s * 2}, s.index[10])
    assert rb.iloc[0].tolist() == [100, 100]
