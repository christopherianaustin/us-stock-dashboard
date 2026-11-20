"""Plain-language explanations: thresholds, sentences, both languages, no buy/sell wording."""
import re

import pytest

from core import plain_language as pl

FORBIDDEN = re.compile(r"\b(buy|sell|beli|jual)\b", re.I)


def test_pe_labels():
    assert pl.pe_ratio(38.9, 0.93).label == "Pricier than usual"
    assert pl.pe_ratio(12.0, 0.10).tone == "good"
    assert pl.pe_ratio(20.0, 0.5).label == "Around its usual level"
    assert "$38.90" in pl.pe_ratio(38.9, 0.93).sentence
    assert pl.pe_ratio(None, None, negative_earnings=True).label == "Not meaningful"


def test_growth_margin_debt_beta_dividend():
    assert pl.revenue_growth(0.12).label == "Growing fast"
    assert pl.revenue_growth(-0.05).tone == "watch"
    assert "12% higher" in pl.revenue_growth(0.12).sentence
    assert pl.net_margin(0.28).label == "Very profitable" and "$0.28" in pl.net_margin(0.28).sentence
    assert pl.net_margin(-0.3).label == "Losing money"
    assert pl.debt_to_equity(0.7).label == "Moderate debt"
    assert pl.debt_to_equity(None, is_financial=True).tone == "na"
    assert pl.beta(1.66).tone == "watch" and pl.beta(1.03).label == "Moves with the market"
    assert pl.dividend_yield(None, pays=False).label == "No dividend"
    assert "$2.19" in pl.dividend_yield(0.0219, pays=True).sentence


@pytest.mark.parametrize("lang", ["en", "id"])
def test_no_buy_sell_wording(lang):
    outs = [pl.pe_ratio(v, p, lang) for v, p in ((10, 0.1), (20, 0.5), (40, 0.9))]
    outs += [pl.pe_ratio(None, None, lang, negative_earnings=True)]
    outs += [pl.revenue_growth(g, lang) for g in (0.2, 0.05, 0.0, -0.1)]
    outs += [pl.net_margin(m, lang) for m in (0.3, 0.1, 0.01, -0.2)]
    outs += [pl.debt_to_equity(d, lang) for d in (0.2, 1.0, 3.0)] + [pl.debt_to_equity(None, lang, True)]
    outs += [pl.dividend_yield(y, True, lang) for y in (0.05, 0.02, 0.005)] + [pl.dividend_yield(None, False, lang)]
    outs += [pl.beta(b, lang) for b in (0.5, 1.0, 1.7)]
    for o in outs:
        assert not FORBIDDEN.search(o.label + " " + o.sentence), o
    if lang == "id":
        assert pl.revenue_growth(0.2, "id").label == "Tumbuh cepat"
