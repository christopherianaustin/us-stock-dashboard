"""Phase 7 acceptance: every test ticker gets a scorecard with explanations, and no buy/sell wording.
Run with:  pytest -m network"""
import re

import pytest

from core.bundle import load_bundle
from core.company import resolve_ticker

pytestmark = pytest.mark.network
FORBIDDEN = re.compile(r"\b(buy|sell|strong buy|strong sell|beli|jual)\b", re.I)


@pytest.mark.parametrize("ticker", ["AAPL", "MSFT", "NVDA", "KO", "TSLA", "JPM", "BRK-B", "PLUG"])
@pytest.mark.parametrize("lang", ["en", "id"])
def test_scorecard_for_every_ticker(ticker, lang):
    b = load_bundle(resolve_ticker(ticker))
    sc = b.scorecard(lang=lang)
    assert sc is not None
    scored = [p for p in sc.pillars.values() if p.score is not None]
    assert len(scored) >= 4, {k: (v.score, v.used) for k, v in sc.pillars.items()}
    assert sc.strengths or sc.risks
    for ins in sc.strengths + sc.risks:
        assert not FORBIDDEN.search(ins.text), ins.text
        assert "{" not in ins.text and "}" not in ins.text
    if ticker in ("TSLA", "PLUG"):
        assert sc.pillars["dividend"].level == "not_applicable"
