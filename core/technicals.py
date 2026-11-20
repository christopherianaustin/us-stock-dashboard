"""Technical indicators, trend signals, support/resistance and pivot points (SPEC 6.8).

All functions take pandas Series/DataFrames with a DatetimeIndex (daily bars, oldest first)
and are pure (no network), so they are easy to test and reuse.
Signals are stated as FACTS ("price is above its 200-day average"), never as advice.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd


# =========================================================================== indicators
def sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n, min_periods=n).mean()


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False, min_periods=n).mean()


def wilder(x: pd.Series, n: int) -> pd.Series:
    """Wilder's smoothing (RMA), as used by RSI and ATR in standard charting tools:
    first value = simple average of the first n values, then avg = (prev x (n-1) + current) / n."""
    vals = x.to_numpy(dtype=float)
    out = np.full(len(vals), np.nan)
    valid = np.flatnonzero(~np.isnan(vals))
    if len(valid) < n:
        return pd.Series(out, index=x.index)
    start = valid[0]
    seed_end = start + n - 1
    out[seed_end] = np.mean(vals[start:seed_end + 1])
    for i in range(seed_end + 1, len(vals)):
        v = vals[i]
        out[i] = out[i - 1] if np.isnan(v) else (out[i - 1] * (n - 1) + v) / n
    return pd.Series(out, index=x.index)


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    """Wilder's RSI: 100 - 100 / (1 + average gain / average loss)."""
    delta = close.diff()
    avg_gain = wilder(delta.clip(lower=0), n)
    avg_loss = wilder(-delta.clip(upper=0), n)
    out = 100 - 100 / (1 + avg_gain / avg_loss)
    out[(avg_loss == 0) & avg_gain.notna()] = 100.0   # only gains -> RSI 100
    return out


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    """MACD line = EMA(fast) - EMA(slow); signal = EMA(signal) of MACD; histogram = MACD - signal."""
    line = close.ewm(span=fast, adjust=False).mean() - close.ewm(span=slow, adjust=False).mean()
    line[: slow - 1] = np.nan
    sig = line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    return pd.DataFrame({"macd": line, "signal": sig, "hist": line - sig})


def bollinger(close: pd.Series, n: int = 20, k: float = 2.0) -> pd.DataFrame:
    """Middle = SMA(n); bands = middle +/- k x standard deviation (population, as most charting tools)."""
    mid = sma(close, n)
    sd = close.rolling(n, min_periods=n).std(ddof=0)
    return pd.DataFrame({"bb_mid": mid, "bb_upper": mid + k * sd, "bb_lower": mid - k * sd})


def atr(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14) -> pd.Series:
    """Average True Range (Wilder). True range = max(high-low, |high-prev close|, |low-prev close|)."""
    prev = close.shift(1)
    tr = pd.concat([high - low, (high - prev).abs(), (low - prev).abs()], axis=1).max(axis=1)
    return wilder(tr, n)


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Adds every indicator column to an OHLCV frame (columns Open, High, Low, Close, Volume)."""
    out = df.copy()
    c = out["Close"]
    for n in (20, 50, 200):
        out[f"sma{n}"] = sma(c, n)
    for n in (12, 26):
        out[f"ema{n}"] = ema(c, n)
    out["rsi14"] = rsi(c, 14)
    out = out.join(macd(c)).join(bollinger(c))
    out["atr14"] = atr(out["High"], out["Low"], c, 14)
    out["vol_avg20"] = sma(out["Volume"], 20)
    out["vol_avg50"] = sma(out["Volume"], 50)
    return out


# =========================================================================== snapshot facts
@dataclass
class TechSnapshot:
    price: float
    as_of: pd.Timestamp
    sma20: Optional[float]
    sma50: Optional[float]
    sma200: Optional[float]
    rsi14: Optional[float]
    macd: Optional[float]
    macd_signal: Optional[float]
    atr14: Optional[float]
    atr_pct: Optional[float]
    volume: Optional[float]
    vol_avg20: Optional[float]
    vol_avg50: Optional[float]
    vol_vs_avg20: Optional[float]
    high_52w: Optional[float]
    low_52w: Optional[float]
    from_high_52w: Optional[float]
    from_low_52w: Optional[float]


def _f(v) -> Optional[float]:
    return None if v is None or pd.isna(v) else float(v)


def snapshot(df: pd.DataFrame) -> TechSnapshot:
    last = df.iloc[-1]
    year = df.tail(252)
    hi, lo = _f(year["High"].max()), _f(year["Low"].min())
    price = float(last["Close"])
    vol, v20 = _f(last.get("Volume")), _f(last.get("vol_avg20"))
    a = _f(last.get("atr14"))
    return TechSnapshot(
        price=price, as_of=df.index[-1], sma20=_f(last.get("sma20")), sma50=_f(last.get("sma50")),
        sma200=_f(last.get("sma200")), rsi14=_f(last.get("rsi14")), macd=_f(last.get("macd")),
        macd_signal=_f(last.get("signal")), atr14=a, atr_pct=(a / price) if a else None, volume=vol,
        vol_avg20=v20, vol_avg50=_f(last.get("vol_avg50")), vol_vs_avg20=(vol / v20) if vol and v20 else None,
        high_52w=hi, low_52w=lo, from_high_52w=(price / hi - 1) if hi else None,
        from_low_52w=(price / lo - 1) if lo else None)


# =========================================================================== trend signals
@dataclass
class Signal:
    name: str
    fact: str
    date: Optional[pd.Timestamp] = None
    tone: str = "neutral"   # positive / negative / neutral (for an icon, never advice)


def _last_cross(a: pd.Series, b: pd.Series, lookback: int) -> Optional[tuple[pd.Timestamp, str]]:
    """Most recent date within `lookback` bars where a crossed b ('up' or 'down')."""
    diff = (a - b).dropna()
    if len(diff) < 2:
        return None
    sign = np.sign(diff)
    changes = sign.ne(sign.shift(1)) & sign.shift(1).notna() & (sign != 0)
    recent = changes[changes].index
    recent = [d for d in recent if d >= diff.index[max(0, len(diff) - lookback)]]
    if not recent:
        return None
    d = recent[-1]
    return d, ("up" if diff.loc[d] > 0 else "down")


def trend_signals(df: pd.DataFrame, lookback: int = 60) -> list[Signal]:
    out: list[Signal] = []
    last = df.iloc[-1]
    price = last["Close"]
    for n in (50, 200):
        m = last.get(f"sma{n}")
        if pd.notna(m):
            above = price > m
            out.append(Signal(f"Price vs {n}-day average",
                              f"Price is {'above' if above else 'below'} its {n}-day average "
                              f"({(price / m - 1) * 100:+.1f}%).",
                              df.index[-1], "positive" if above else "negative"))
    cross = _last_cross(df["sma50"], df["sma200"], lookback)
    if cross:
        d, direction = cross
        if direction == "up":
            out.append(Signal("Golden cross", "The 50-day average crossed above the 200-day average "
                              "(often read as a sign of strengthening trend).", d, "positive"))
        else:
            out.append(Signal("Death cross", "The 50-day average crossed below the 200-day average "
                              "(often read as a sign of weakening trend).", d, "negative"))
    else:
        out.append(Signal("50/200-day cross", f"No golden or death cross in the last {lookback} trading days."))
    r = last.get("rsi14")
    if pd.notna(r):
        if r > 70:
            out.append(Signal("RSI", f"RSI is {r:.0f}, in the 'overbought zone' (above 70). Prices rose fast recently.",
                              df.index[-1], "negative"))
        elif r < 30:
            out.append(Signal("RSI", f"RSI is {r:.0f}, in the 'oversold zone' (below 30). Prices fell fast recently.",
                              df.index[-1], "positive"))
        else:
            out.append(Signal("RSI", f"RSI is {r:.0f}, in the neutral range (30-70).", df.index[-1]))
    cross = _last_cross(df["macd"], df["signal"], lookback)
    if cross:
        d, direction = cross
        out.append(Signal("MACD crossover",
                          f"MACD crossed {'above' if direction == 'up' else 'below'} its signal line "
                          f"({'upward' if direction == 'up' else 'downward'} momentum shift).",
                          d, "positive" if direction == "up" else "negative"))
    else:
        out.append(Signal("MACD crossover", f"No MACD crossover in the last {lookback} trading days."))
    return out


# =========================================================================== support / resistance
@dataclass
class Level:
    price: float
    kind: str               # "support" or "resistance"
    strength: float
    touches: int
    last_touch: pd.Timestamp
    distance: float         # (level / current price) - 1
    rank: int = 0


@dataclass
class SRResult:
    supports: list[Level] = field(default_factory=list)
    resistances: list[Level] = field(default_factory=list)
    tolerance: float = 0.0
    window: str = "1y"

    @property
    def nearest_support(self) -> Optional[Level]:
        return self.supports[0] if self.supports else None

    @property
    def nearest_resistance(self) -> Optional[Level]:
        return self.resistances[0] if self.resistances else None


def swing_points(df: pd.DataFrame, window: int = 5) -> pd.DataFrame:
    """Swing high: the bar's High is the highest of `window` bars on each side (low: same with Low).
    The last `window` bars can't be confirmed yet, so they are skipped."""
    hi, lo = df["High"], df["Low"]
    size = 2 * window + 1
    is_high = hi == hi.rolling(size, center=True, min_periods=size).max()
    is_low = lo == lo.rolling(size, center=True, min_periods=size).min()
    rows = [{"date": d, "price": float(hi[d]), "type": "high"} for d in hi.index[is_high]]
    rows += [{"date": d, "price": float(lo[d]), "type": "low"} for d in lo.index[is_low]]
    return pd.DataFrame(rows, columns=["date", "price", "type"]).sort_values("date").reset_index(drop=True)


def support_resistance(df: pd.DataFrame, window: str = "1y", swing: int = 5, keep: int = 3) -> SRResult:
    """1) swing highs/lows over the window  2) cluster within max(0.5 x ATR, 1.5% of price)
    3) strength = touches weighted by recency and volume  4) keep `keep` strongest each side."""
    bars = {"6m": 126, "1y": 252, "2y": 504}[window]
    data = df.tail(bars)
    if len(data) < 2 * swing + 2:
        return SRResult(window=window)
    price = float(data["Close"].iloc[-1])
    atr_now = data["atr14"].iloc[-1] if "atr14" in data else np.nan
    tol = max(0.5 * atr_now if pd.notna(atr_now) else 0.0, 0.015 * price)
    pts = swing_points(data, swing)
    # The window's highest high and lowest low (e.g. a fresh 52-week high) always count as touch
    # points, even when they are too recent to be confirmed swing points (need `swing` bars after).
    extremes = [{"date": data["High"].idxmax(), "price": float(data["High"].max()), "type": "high"},
                {"date": data["Low"].idxmin(), "price": float(data["Low"].min()), "type": "low"}]
    extra = [e for e in extremes if not ((pts["date"] == e["date"]) & (pts["type"] == e["type"])).any()]
    if extra:
        pts = pd.concat([pts, pd.DataFrame(extra)], ignore_index=True)
    if pts.empty:
        return SRResult(window=window, tolerance=tol)

    # Weights: recent touches up to 2x; touches on high volume (> 1.5x the 50-day average) x1.5
    pos = {d: i for i, d in enumerate(data.index)}
    vol = data["Volume"]
    vavg = vol.rolling(50, min_periods=10).mean()
    pts["w"] = [(1 + pos[d] / len(data)) * (1.5 if pd.notna(vavg[d]) and vol[d] > 1.5 * vavg[d] else 1.0)
                for d in pts["date"]]

    # Greedy clustering on sorted prices. A cluster never spans more than `tol` from its lowest
    # point, so a zone can't drift upward and swallow distant levels.
    clusters: list[list[int]] = []
    for i in pts.sort_values("price").index:
        p = pts.at[i, "price"]
        if clusters and p - pts.at[clusters[-1][0], "price"] <= tol:
            clusters[-1].append(i)
        else:
            clusters.append([i])

    levels = []
    for c in clusters:
        sub = pts.loc[c]
        lvl = float(sub["price"].mean())
        if abs(lvl / price - 1) < 0.002:   # a level at today's price is neither support nor resistance
            continue
        levels.append(Level(price=lvl, kind="support" if lvl < price else "resistance",
                            strength=round(float(sub["w"].sum()), 2), touches=len(sub),
                            last_touch=sub["date"].max(), distance=lvl / price - 1))
    sup = sorted([l for l in levels if l.kind == "support"], key=lambda l: -l.strength)[:keep]
    res = sorted([l for l in levels if l.kind == "resistance"], key=lambda l: -l.strength)[:keep]
    sup.sort(key=lambda l: -l.price)     # nearest first
    res.sort(key=lambda l: l.price)
    for i, l in enumerate(sup, 1):
        l.rank = i
    for i, l in enumerate(res, 1):
        l.rank = i
    return SRResult(supports=sup, resistances=res, tolerance=tol, window=window)


def weekly_pivots(df: pd.DataFrame) -> Optional[dict]:
    """Classic pivot points from the previous COMPLETE week: P = (H+L+C)/3, R1 = 2P-L, S1 = 2P-H,
    R2 = P + (H-L), S2 = P - (H-L)."""
    if df.empty:
        return None
    wk = df.resample("W-FRI").agg({"High": "max", "Low": "min", "Close": "last"}).dropna()
    last_day = df.index[-1]
    # Each week is labeled by its Friday. The latest week is complete only if the last bar is a Friday.
    this_week = last_day + pd.Timedelta(days=(4 - last_day.weekday()) % 7)
    complete = wk[wk.index <= this_week] if last_day.weekday() == 4 else wk[wk.index < this_week]
    if complete.empty:
        return None
    w = complete.iloc[-1]
    h, l, c = float(w["High"]), float(w["Low"]), float(w["Close"])
    p = (h + l + c) / 3
    return {"week_ending": complete.index[-1], "P": p, "R1": 2 * p - l, "S1": 2 * p - h,
            "R2": p + (h - l), "S2": p - (h - l)}
