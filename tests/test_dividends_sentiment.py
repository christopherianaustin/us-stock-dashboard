"""Phase 6 unit tests (no internet): dividends, holders, insiders, analyst ratings, news."""
import pandas as pd
import pytest

from core.dividends import (annual_dps, dividend_cagr, growth_streak, pays_dividend, payments_per_year, summarize,
                            ttm_dps, yield_history)
from core.sentiment import (classify_insider, clean_news, consensus_summary, holder_breakdown, insider_monthly_net,
                            insider_table, news_from_finnhub, news_from_yfinance, recommendations_from_finnhub,
                            recommendations_from_yfinance, upgrades_table)

T = pd.Timestamp
THIS_YEAR = pd.Timestamp.today().year


def _quarterly_divs(start_year: int, amounts: dict[int, float]) -> pd.Series:
    idx, vals = [], []
    for y, amt in amounts.items():
        for m in (3, 6, 9, 12):
            if T(y, m, 15) <= pd.Timestamp.today():
                idx.append(T(y, m, 15))
                vals.append(amt)
    return pd.Series(vals, index=pd.DatetimeIndex(idx))


def _growing(years=8, start=1.0, g=0.05):
    first = THIS_YEAR - years
    return _quarterly_divs(first, {first + i: round(start * (1 + g) ** i, 4) for i in range(years + 1)})


# ---------------------------------------------------------------- dividends
def test_no_dividend_and_stopped_dividend():
    pays, reason = pays_dividend(pd.Series(dtype=float))
    assert not pays and reason == "This company does not pay a dividend."
    old = pd.Series([0.5], index=[T("2019-03-01")])
    pays, reason = pays_dividend(old)
    assert not pays and "2019" in reason


def test_ttm_dps_and_frequency():
    d = _growing()
    assert payments_per_year(d) == 4
    last_year = d[d.index > d.index.max() - pd.Timedelta(days=365)]
    assert ttm_dps(d) == pytest.approx(last_year.sum())


def test_annual_dps_excludes_current_year():
    a = annual_dps(_growing())
    assert a.index.max() == THIS_YEAR - 1
    assert a.iloc[-1] == pytest.approx(4 * round(1.0 * 1.05 ** 7, 4))


def test_dividend_cagr():
    assert dividend_cagr(_growing(g=0.05), 5) == pytest.approx(0.05, abs=0.002)
    assert dividend_cagr(_growing(years=2), 5) is None


def test_growth_streak_counts_raises_and_stops_at_a_cut():
    first = THIS_YEAR - 6
    amounts = {first: 1.0, first + 1: 1.1, first + 2: 1.0, first + 3: 1.05, first + 4: 1.1, first + 5: 1.2, first + 6: 1.3}
    assert growth_streak(_quarterly_divs(first, amounts)) == 3   # raises in the last 3 complete years


def test_growth_streak_ignores_special_dividend():
    first = THIS_YEAR - 4
    d = _quarterly_divs(first, {first + i: 1.0 + 0.1 * i for i in range(5)})
    d = pd.concat([d, pd.Series([5.0], index=[T(first + 1, 7, 1)])]).sort_index()   # one-off special
    assert growth_streak(d) == 3


def test_growth_streak_counts_raise_in_last_payment():
    first = THIS_YEAR - 3
    d = pd.Series([0.13] * 4 + [0.13, 0.13, 0.13, 0.16] + [0.16, 0.16, 0.16, 0.20],
                  index=pd.DatetimeIndex([T(first + y, m, 15) for y in range(3) for m in (3, 6, 9, 12)]))
    assert growth_streak(d) == 2


def test_yield_history_and_summary():
    idx = pd.bdate_range(T(THIS_YEAR - 2, 1, 1), pd.Timestamp.today())
    close = pd.Series(100.0, index=idx)
    d = _quarterly_divs(THIS_YEAR - 2, {THIS_YEAR - 2: 0.5, THIS_YEAR - 1: 0.5, THIS_YEAR: 0.5})
    y = yield_history(d, close)
    assert y.dropna().iloc[-1] == pytest.approx(ttm_dps(d, y.dropna().index[-1]) / 100)
    s = summarize(d, close, 100.0)
    assert s.pays and s.frequency == 4 and s.yield_ttm == pytest.approx(s.dps_ttm / 100)


# ---------------------------------------------------------------- holders / insiders
def test_holder_breakdown():
    major = pd.DataFrame({"Value": [0.1, 0.7, 0.75, 4736]},
                         index=["insidersPercentHeld", "institutionsPercentHeld", "institutionsFloatPercentHeld",
                                "institutionsCount"])
    b = holder_breakdown(major)
    assert b == pytest.approx({"Insiders": 0.1, "Institutions": 0.7, "Other / public": 0.2})
    assert holder_breakdown(None) is None


def test_classify_insider():
    assert classify_insider("Sale at price 99.40 per share.") == "sell"
    assert classify_insider("Purchase at price 10.00 per share.") == "buy"
    assert classify_insider("Stock Award(Grant) at price 0.00 per share.") == "other"
    assert classify_insider("Conversion of Exercise of derivative security") == "other"
    assert classify_insider(None) == "other"


def test_insider_monthly_net():
    m0 = pd.Timestamp.today().to_period("M").to_timestamp()
    tx = pd.DataFrame({"Start Date": [m0 + pd.Timedelta(days=1), m0 + pd.Timedelta(days=2), m0 + pd.Timedelta(days=3)],
                       "Insider": ["A", "B", "C"], "Position": ["CEO", "CFO", "Director"],
                       "Text": ["Sale at price 10", "Purchase at price 9", "Stock Gift"],
                       "Shares": [100, 50, 10], "Value": [1000, 450, 0]})
    t = insider_table(tx)
    assert list(t["type"]) == ["other", "buy", "sell"]           # newest first
    m = insider_monthly_net(t)
    assert m.loc[m0, "bought"] == 450 and m.loc[m0, "sold"] == -1000 and m.loc[m0, "net"] == -550


# ---------------------------------------------------------------- analysts
def test_recommendations_and_consensus():
    fh = recommendations_from_finnhub([
        {"period": "2026-10-01", "strongBuy": 8, "buy": 19, "hold": 7, "sell": 0, "strongSell": 0},
        {"period": "2026-11-01", "strongBuy": 8, "buy": 20, "hold": 7, "sell": 0, "strongSell": 0}])
    assert list(fh["month"]) == [T("2026-10-01"), T("2026-11-01")]
    c = consensus_summary(fh)
    assert c["total"] == 35 and c["mean_score"] == pytest.approx((8 + 40 + 21) / 35)
    yf = recommendations_from_yfinance(pd.DataFrame({"period": ["0m", "-1m"], "strongBuy": [1, 1], "buy": [2, 2],
                                                     "hold": [3, 3], "sell": [0, 0], "strongSell": [0, 0]}),
                                       today=T("2026-11-20"))
    assert list(yf["month"]) == [T("2026-10-01"), T("2026-11-01")]


def test_upgrades_table():
    df = pd.DataFrame({"Firm": ["TD Cowen", "Wolfe"], "ToGrade": ["Buy", "Outperform"], "FromGrade": ["Buy", ""],
                       "Action": ["main", "init"], "currentPriceTarget": [112.0, 0.0], "priorPriceTarget": [104.0, 0.0]},
                      index=pd.Index([T("2026-11-17"), T("2026-11-18")], name="GradeDate"))
    t = upgrades_table(df)
    assert list(t["firm"]) == ["Wolfe", "TD Cowen"]
    assert t.iloc[1]["price target"] == "$104 → $112" and t.iloc[0]["action"] == "Initiated"


# ---------------------------------------------------------------- news
def test_news_normalize_dedupe_and_filter():
    now = pd.Timestamp.now(tz="UTC")
    fh = news_from_finnhub([
        {"datetime": int(now.timestamp()) - 3600, "headline": "KO beats estimates", "source": "Yahoo", "url": "u1"},
        {"datetime": int(now.timestamp()) - 7200, "headline": "KO Beats Estimates!", "source": "X", "url": "u2"},
        {"datetime": int((now - pd.Timedelta(days=20)).timestamp()), "headline": "Old story", "source": "Y", "url": "u3"},
        {"datetime": int(now.timestamp()), "headline": "", "url": "u4"}])
    assert len(fh) == 3
    week = clean_news(fh, days=7)
    assert [n["headline"] for n in week] == ["KO beats estimates"]
    assert len(clean_news(fh, days=30)) == 2
    yf = news_from_yfinance([{"content": {"title": "T", "pubDate": "2026-11-20T00:17:34Z",
                                          "provider": {"displayName": "P"}, "clickThroughUrl": {"url": "https://x"},
                                          "thumbnail": {"resolutions": [{"url": "big", "tag": "original"},
                                                                        {"url": "small", "tag": "170x128"}]}}}])
    assert yf[0]["image"] == "small" and yf[0]["source"] == "P"
