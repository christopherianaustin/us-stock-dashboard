"""Phase 7 unit tests (no internet): scoring, levels, strengths/risks, languages, no buy/sell wording."""
import re
import string

import pytest
import yaml

from config.settings import CONFIG_DIR
from core.scorecard import (DEMO_FACTS, PILLARS, build_scorecard, format_values, generate_insights, insight_texts,
                            level_for, score_metric, score_pillars, scoring_config)

FORBIDDEN = {
    "en": re.compile(r"\b(buy|sell|strong buy|strong sell|outperform|underperform|overweight|underweight)\b", re.I),
    "id": re.compile(r"\b(beli|jual|buy|sell)\b", re.I),
}


def test_score_metric_linear_and_clamped():
    assert score_metric(0.15, "higher_better", [-0.05, 0.15]) == 100
    assert score_metric(-0.05, "higher_better", [-0.05, 0.15]) == 0
    assert score_metric(0.05, "higher_better", [-0.05, 0.15]) == 50
    assert score_metric(0.5, "lower_better", [0.5, 2.0]) == 100
    assert score_metric(2.5, "lower_better", [0.5, 2.0]) == 0
    assert score_metric(1.25, "lower_better", [0.5, 2.0]) == 50


def test_levels():
    assert level_for(70) == "strong" and level_for(69.9) == "neutral" and level_for(40) == "neutral"
    assert level_for(39) == "weak" and level_for(None) is None


GOOD = {"revenue_yoy": 0.2, "eps_yoy": 0.3, "revenue_cagr_3y": 0.15, "forward_growth": 0.2, "net_margin": 0.25,
        "roe": 0.3, "roic": 0.2, "net_margin_change": 0.03, "net_income_ttm": 1e9, "pays_dividend": 0.0}


def test_pillar_scores_and_based_on():
    p = score_pillars(GOOD)
    assert p["growth"].score == 100 and p["growth"].level == "strong" and p["growth"].used == 4
    assert p["profitability"].level == "strong"
    assert p["valuation"].score is None and p["valuation"].level is None       # no inputs
    assert p["dividend"].level == "not_applicable"


def test_pillar_needs_two_metrics():
    p = score_pillars({"revenue_yoy": 0.2})
    assert p["growth"].score is None and p["growth"].used == 1


def test_insights_text_and_order():
    facts = {**GOOD, "beats_8": 7, "quarters_8": 8, "beat_rate_8": 0.875, "pe_percentile": 0.85, "net_debt": -5e9}
    strengths, risks = generate_insights(facts, "en")
    texts = [s.text for s in strengths]
    assert "Revenue grew 20% compared with the same quarter last year." in texts
    assert "The company beat EPS estimates in 7 of the last 8 quarters." in texts
    assert len(strengths) <= 5
    assert risks[0].text == ("P/E is higher than 85% of the last 5 years, so the stock is priced more "
                             "expensively than usual.")
    assert [s.priority for s in strengths] == sorted([s.priority for s in strengths], reverse=True)


def test_negative_eps_growth_not_called_growth_when_losing_money():
    facts = {"eps_yoy": 1.0, "net_income_ttm": -1e9}
    strengths, risks = generate_insights(facts, "en")
    assert all(s.id != "eps_growth" for s in strengths)
    assert any(r.id == "losing_money" for r in risks)


def test_negative_interest_coverage_message():
    _, risks = generate_insights({"interest_coverage": -13.5}, "en")
    ids = [r.id for r in risks]
    assert "no_coverage" in ids and "low_coverage" not in ids


def test_indonesian_texts():
    strengths, _ = generate_insights({"revenue_yoy": 0.2}, "id")
    assert strengths[0].text.startswith("Pendapatan tumbuh 20%")
    sc = build_scorecard(GOOD, "id")
    assert insight_texts("id")["levels"][sc.pillars["growth"].level] == "Kuat"


def test_safe_mode_drops_demo_facts():
    facts = {**GOOD, "vs_sma50": 0.1, "vs_sma200": 0.2, "rel_strength_6m": 0.2, "from_52w_high": -0.01}
    assert build_scorecard(facts, safe_mode=False).pillars["momentum"].score == 100
    sc = build_scorecard(facts, safe_mode=True)
    assert sc.pillars["momentum"].score is None and not (set(sc.facts) & DEMO_FACTS)


@pytest.mark.parametrize("lang", ["en", "id"])
def test_every_template_renders_and_rule_has_text(lang):
    cfg, texts = scoring_config(), insight_texts(lang)
    all_facts = {k: 0.5 for k in ["revenue_yoy", "eps_yoy", "beats_8", "quarters_8", "net_margin", "roe", "net_debt",
                                  "pe_percentile", "pe_vs_peers", "piotroski_score", "growth_streak", "rel_strength_6m",
                                  "fcf_yield", "estimate_change_90d", "altman_z", "cash_conversion", "net_income_ttm",
                                  "net_debt_to_ebitda", "interest_coverage", "beat_rate_8", "vs_sma200", "payout_ratio",
                                  "volatility", "current_drawdown", "short_pct"]}
    values = format_values(all_facts)
    for kind in ("strengths", "risks"):
        for rule in cfg[kind]:
            assert rule["id"] in texts[kind], f"{lang}: missing text for {rule['id']}"
            texts[kind][rule["id"]].format(**values)   # raises if a placeholder is unknown
    for m in sum((list(p["metrics"]) for p in cfg["pillars"].values()), []):
        assert m in texts["metrics"], f"{lang}: missing metric label {m}"
    for p in PILLARS:
        assert p in texts["pillars"] and p in texts["pillar_help"]


@pytest.mark.parametrize("lang", ["en", "id"])
def test_no_buy_sell_wording_in_our_texts(lang):
    """Our own wording must never be a buy/sell verdict (SPEC hard rule 1)."""
    with open(CONFIG_DIR / f"insights_{lang}.yaml", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    def strings(x):
        if isinstance(x, dict):
            for v in x.values():
                yield from strings(v)
        elif isinstance(x, list):
            for v in x:
                yield from strings(v)
        elif isinstance(x, str):
            yield x

    for s in strings(data):
        assert not FORBIDDEN[lang].search(s), f"forbidden wording in {lang}: {s}"
