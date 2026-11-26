"""Phase 10a tests: validator, input builder, cache key, client and service. No network, no API spend:
the Anthropic SDK is replaced by a fake object."""
from __future__ import annotations

import copy
import json
from types import SimpleNamespace

import diskcache
import pytest

from config.settings import Settings
from core.ai_summary import cache, client as client_mod, service
from core.ai_summary.client import AIClient, AIRefused, user_message
from core.ai_summary.input_builder import TABS, build_tab_input, round_sig, rule_signal
from core.ai_summary.schema import TabSummary
from core.ai_summary.validator import check_banned, check_lengths, check_numbers, validate
from tests.ai_fixtures import INSIGHTS, pillars, sections

TICKERS = ("AAPL", "KO", "TSLA", "JPM")


def pt(detail: str, title: str = "Priced above its history") -> dict:
    return {"title": title, "detail": detail, "metric_keys": []}


def make(text: str | None = None, **kw) -> TabSummary:
    """A summary; `text` becomes the detail of one bearish point (handy for the word checks)."""
    base = dict(bullish=[pt("Investors pay more than usual for each dollar of profit.", "Steady profit record")],
                bearish=[pt(text)] if text is not None else [], data_gaps=[])
    base.update(kw)
    return TabSummary.model_validate(base)


def tab_input(ticker="AAPL", tab="valuation", **kw):
    return build_tab_input(tab, sections(ticker), ticker=ticker, pillars=pillars(ticker), insights=INSIGHTS, **kw)


# =========================================================================== validator: banned phrases
@pytest.mark.parametrize("text", [
    "You should buy before earnings.", "The stock looks undervalued.", "The price will rise next year.",
    "A real bargain at this level.", "Profit is guaranteed.", "Saham ini murah dibanding sejenis.",
    "Sebaiknya Anda menunggu.", "Investors may want to hold.", "It is a sure thing.",
])
def test_banned_phrases_are_caught(text):
    assert check_banned(make(text), "valuation")


@pytest.mark.parametrize("text", [
    "Buybacks returned cash to shareholders.", "Insiders were selling shares last month.",
    "Penjualan naik 12%.", "The company holds more cash than debt.", "Margins are steady.",
])
def test_ordinary_words_are_not_banned(text):
    assert check_banned(make(text), "valuation") == []


def test_analyst_exception_only_in_ownership_and_earnings():
    s = make(bullish=[pt("Wall Street analysts rate it a buy: 30 of 49 analysts.")])
    assert check_banned(s, "ownership_sentiment") == []
    assert check_banned(s, "earnings") == []
    assert check_banned(s, "valuation")            # same sentence is not allowed in other tabs
    s_id = make(bullish=[pt("Sebanyak 30 dari 49 analis menilai beli.")])
    assert check_banned(s_id, "ownership_sentiment") == []
    # the exception covers only the attributed sentence, not the rest
    s2 = make("Analysts rate it a buy. You should buy too.")
    assert check_banned(s2, "ownership_sentiment")


# =========================================================================== validator: numbers
PAYLOAD = {"metrics": [{"key": "pe", "value": 39.476, "compare": {"own_5y_percentile": 95.9}},
                       {"key": "price", "value": 5948000, "unit": "IDR per share"},
                       {"key": "margin", "value": 12.5, "unit": "%"}],
           "upcoming_events": {"next_earnings_date": "2027-01-28"},
           "last_quarters": [{"quarter": "Q4 FY26"}], "beat": "8 of 8"}


@pytest.mark.parametrize("text", [
    "P/E is 39.5.", "P/E is about 39.", "Higher than 96% of the last 5 years.", "Margin is 12,5%.",
    "Price is Rp5.948.000.", "Price is Rp5,948,000.", "Next report on 28 Jan 2027.", "Beat estimates in 8 of 8 quarters.",
    "In Q4 FY26 results improved.", "Keeps $12 of every $100 in sales.",
])
def test_numbers_from_the_data_pass(text):
    assert check_numbers(make(text), PAYLOAD) == []


@pytest.mark.parametrize("text", ["P/E is 40.", "Margin is 57%.", "Price is Rp6.100.000.", "Next report in 2028."])
def test_numbers_not_in_the_data_fail(text):
    assert check_numbers(make(text), PAYLOAD)


# =========================================================================== validator: lengths (SPEC 16.6)
def test_length_limits():
    assert check_lengths(make("P/E is 39.5.")) == []
    assert check_lengths(make(bullish=[pt("a")] * 5))                                   # max 4 per list
    assert check_lengths(make(bearish=[pt("x", title="Expensive")]))                    # title 2-6 words
    assert check_lengths(make(bearish=[pt("x", title="one two three four five six seven")]))
    assert check_lengths(make(" ".join(["w"] * 26)))                                    # detail max 25 words
    assert check_lengths(make("One sentence. Then another."))                           # detail is one sentence
    assert check_lengths(make(data_gaps=["a", "b", "c", "d"]))                          # data_gaps max 3
    assert check_lengths(make(bullish=[], bearish=[])) == []                            # empty lists are allowed


def test_bullish_and_bearish_words_are_allowed():
    s = make("Bearish point: P/E is 39.5.", bullish=[pt("Bullish point on margins.", "Bullish margin trend")])
    assert check_banned(s, "valuation") == []


def test_validate_combines_all_checks():
    good = make("P/E is 39.5, higher than 96% of the last 5 years.")
    assert validate(good, PAYLOAD, "valuation").ok
    bad = make("Looks undervalued at 41x, so it is a good time to buy before results come in next quarter and beyond.",
               bullish=[pt("x", title="Cheap")])
    r = validate(bad, PAYLOAD, "valuation")
    assert not r.ok and len(r.failures) >= 3


# =========================================================================== input builder
@pytest.mark.parametrize("ticker", TICKERS)
def test_every_tab_builds_and_stays_small(ticker):
    for tab in TABS:
        ti = tab_input(ticker, tab)
        text = json.dumps(ti.payload, ensure_ascii=False, separators=(",", ":"))
        assert len(text) / 4 < 3000, f"{ticker} {tab} input is too big"
        assert ti.payload["ticker"] == ticker and ti.payload["tab"] == tab
        assert ti.license_tag in ("COMMERCIAL_OK", "CALCULATED_SAFE", "DEMO_ONLY")


def test_numbers_are_rounded_and_ratios_become_percent():
    assert round_sig(39.476498) == 39.5 and round_sig(0.0302200) == 0.0302 and round_sig(1254) == 1250
    m = {x["key"]: x for x in tab_input("AAPL", "valuation").payload["metrics"]}
    assert m["pe"]["value"] == 39.5 and m["pe"]["unit"] == "x"
    assert m["pe"]["compare"]["own_5y_percentile"] == 95.9 and m["pe"]["compare"]["peer_median"] == 20.8
    assert m["fcf_yield"]["unit"] == "%" and 1 < m["fcf_yield"]["value"] < 10
    assert m["market_cap"]["unit"].startswith("USD ") and m["market_cap"]["value"] < 1000


def test_rupiah_needs_a_rate_and_marks_demo():
    ti = tab_input("AAPL", "valuation", lang="id", currency="IDR", fx=16800.0)
    price = next(x for x in ti.payload["metrics"] if x["key"] == "price")
    assert price["unit"] == "IDR per share" and price["value"] > 1_000_000
    assert ti.license_tag == "DEMO_ONLY" and ti.payload["exchange_rate_used"]["usd_idr"] == 16800
    no_rate = tab_input("AAPL", "valuation", lang="id", currency="IDR", fx=None)
    assert next(x for x in no_rate.payload["metrics"] if x["key"] == "price")["unit"] == "USD per share"


def test_news_sends_only_headline_source_date_max_15():
    p = tab_input("AAPL", "news_filings").payload
    assert 0 < len(p["headlines"]) <= 15
    assert all(set(h) <= {"headline", "source", "date"} for h in p["headlines"])
    assert len(p["sec_filings"]) <= 10


def test_missing_data_is_listed():
    tsla = tab_input("TSLA", "dividends").payload
    assert tsla["pays_dividend"] is False
    jpm = tab_input("JPM", "profitability_health").payload
    assert any(m["key"] == "gross_margin" for m in jpm["missing"])
    assert "bank" in jpm.get("note", "")


def _redact(o):
    """What production-safe mode does to the data (same rule as the API and the mobile prototype)."""
    if isinstance(o, list):
        return [_redact(x) for x in o]
    if isinstance(o, dict):
        if o.get("license_tag") == "DEMO_ONLY":
            if "items" in o:
                return {**o, "available": False, "items": [], "na_reason": "Requires a licensed data provider"}
            if "value" in o:
                return {**o, "value": None, "na_reason": "Requires a licensed data provider"}
        return {k: _redact(v) for k, v in o.items()}
    return o


def test_safe_mode_sends_only_licensed_or_calculated_data():
    s = _redact(copy.deepcopy(sections("AAPL")))
    for tab in TABS:
        ti = build_tab_input(tab, s, ticker="AAPL", pillars=pillars("AAPL"), insights=INSIGHTS)
        assert all(m["license_tag"] != "DEMO_ONLY" for m in ti.payload.get("metrics", [])), tab
        assert ti.license_tag in ("COMMERCIAL_OK", "CALCULATED_SAFE"), tab


def test_rule_signal_per_tab():
    p = {"valuation": {"score": 7, "level": "weak"}, "momentum": {"score": 80, "level": "strong"},
         "profitability": {"score": 90, "level": "strong"}, "financial_health": {"score": 50, "level": "neutral"},
         "dividend": {"score": None, "level": "not_applicable"}}
    assert rule_signal(p, "valuation") == "Weak"
    assert rule_signal(p, "price_technicals") == "Strong"
    assert rule_signal(p, "profitability_health") == "Strong"          # average of 90 and 50
    assert rule_signal(p, "dividends") == "Not applicable"
    assert rule_signal(p, "news_filings") == "Not applicable"
    assert rule_signal(p, "earnings") == "Not enough data"


# =========================================================================== cache key
def test_cache_key():
    a = {"ticker": "AAPL", "metrics": [{"key": "pe", "value": 39.5}], "as_of": "2026-11-25T01:00:00"}
    same_but_later = {**a, "as_of": "2026-11-25T09:00:00"}
    new_price = {**a, "metrics": [{"key": "pe", "value": 40.1}]}
    k = cache.cache_key("aapl", "valuation", "en", a, "1.0")
    assert k == cache.cache_key("AAPL", "valuation", "en", same_but_later, "1.0")    # time stamp only
    assert k != cache.cache_key("AAPL", "valuation", "en", new_price, "1.0")          # data changed
    assert k != cache.cache_key("AAPL", "valuation", "id", a, "1.0")
    assert k != cache.cache_key("AAPL", "earnings", "en", a, "1.0")
    assert k != cache.cache_key("AAPL", "valuation", "en", a, "1.1")                  # new prompt version
    assert k.startswith("ai|AAPL|valuation|en|v1.0|")


# =========================================================================== prompt and client (fake SDK)
def test_user_message_follows_the_template():
    ti = tab_input()
    msg = user_message("valuation", "id", "IDR", ti.payload)
    for part in ("<request>", "tab: Valuation", "tab_focus: How the price compares", "language: id",
                 'currency: "IDR"', '"Rp1,234,567"', '"12.5%"', "<stock_data>", "</stock_data>",
                 "Write the summary for this tab."):
        assert part in msg


GOOD = make("P/E (price compared with yearly profit) of 39.5 is higher than 96% of the last 5 years.",
            bullish=[pt("Peer median P/E is 20.8, compared with 39.5 for this stock.", "Peer comparison available")])


class FakeSDK:
    """Stands in for anthropic.Anthropic: returns queued answers, records the request."""

    def __init__(self, *answers):
        self.answers, self.calls = list(answers), []
        self.beta = SimpleNamespace(messages=SimpleNamespace(parse=self._parse))

    def _parse(self, **kw):
        self.calls.append(kw)
        a = self.answers.pop(0)
        if isinstance(a, Exception):
            raise a
        stop = "refusal" if a == "refusal" else "end_turn"
        return SimpleNamespace(
            stop_reason=stop, stop_details=SimpleNamespace(category="other") if stop == "refusal" else None,
            parsed_output=None if stop == "refusal" else a, model=kw["model"], _request_id="req_test",
            usage=SimpleNamespace(input_tokens=1000, output_tokens=400, cache_creation_input_tokens=1500,
                                  cache_read_input_tokens=0, iterations=None))


def cfg(**kw) -> Settings:
    return Settings(anthropic_api_key="test-key", **kw)


def test_client_request_shape():
    sdk = FakeSDK(GOOD)
    r = AIClient(cfg(), sdk=sdk).summarize("hello")
    kw = sdk.calls[0]
    assert kw["model"] == "claude-opus-5-5" and kw["output_format"] is TabSummary
    assert kw["output_config"] == {"effort": "medium"}
    assert kw["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert kw["fallbacks"] == "default" and kw["betas"] == ["server-side-fallback-2026-07-01"]
    assert r.summary.bearish == GOOD.bearish and r.usage.total == 2900


def test_client_raises_on_refusal_and_skips_fallbacks_for_other_models():
    with pytest.raises(AIRefused):
        AIClient(cfg(), sdk=FakeSDK("refusal")).summarize("hello")
    sdk = FakeSDK(GOOD)
    AIClient(cfg(ai_model="claude-haiku-5-5"), sdk=sdk).summarize("hello")
    assert "fallbacks" not in sdk.calls[0]


def test_cost_estimate():
    u = client_mod.Usage(input_tokens=1_000_000, output_tokens=100_000)
    assert client_mod.cost_usd(u, "claude-opus-5-5") == pytest.approx(4.0 + 2.0)
    assert client_mod.cost_usd(u, "unknown-model") is None


# =========================================================================== service: cache, retry, fallback
@pytest.fixture
def tmp_store(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "_cache", diskcache.Cache(str(tmp_path / "c")))
    monkeypatch.setattr(service, "LOG_FILE", tmp_path / "ai.jsonl")
    monkeypatch.setattr(service, "LOG_DIR", tmp_path)
    return tmp_path


def run(sdk, ti=None, **kw):
    ti = ti or tab_input()
    return service.get_summary("AAPL", "valuation", "en", "USD", ti, cfg=kw.pop("cfg", cfg()),
                               client=AIClient(cfg(), sdk=sdk), **kw)


def test_service_ai_result_is_cached_and_logged(tmp_store):
    sdk = FakeSDK(GOOD)
    first = run(sdk)
    assert first["source"] == "ai" and first["attempts"] == 1 and first["cost_usd"] > 0
    second = run(FakeSDK())          # no answers queued: must come from the cache
    assert second["cached"] is True and second["summary"] == first["summary"]
    log = [json.loads(x) for x in (tmp_store / "ai.jsonl").read_text(encoding="utf-8").splitlines()]
    assert log[0]["result"] == "passed" and log[0]["usage"]["total"] == 2900 and log[0]["prompt_version"]


def test_service_retries_once_with_a_note(tmp_store):
    bad = make("The stock is undervalued.")
    sdk = FakeSDK(bad, GOOD)
    out = run(sdk)
    assert out["source"] == "ai" and out["attempts"] == 2
    assert "previous answer failed these checks" in sdk.calls[1]["messages"][0]["content"]


def test_service_falls_back_after_two_failures_or_a_refusal(tmp_store):
    bad = make("You should buy now.")
    out = run(FakeSDK(bad, bad))
    assert out["source"] == "fallback" and out["summary"]["label"] == "Automatic summary"
    assert out["summary"]["bearish"] == ["P/E is higher than 96% of the last 5 years."]
    ti = tab_input("KO")
    out2 = service.get_summary("KO", "valuation", "en", "USD", ti, cfg=cfg(), client=AIClient(cfg(), sdk=FakeSDK("refusal")))
    assert out2["source"] == "fallback"


def test_service_off_when_disabled_or_no_key(tmp_store):
    assert run(FakeSDK(), cfg=Settings(anthropic_api_key=""))["enabled"] is False
    assert run(FakeSDK(), cfg=Settings(anthropic_api_key="k", ai_summaries_enabled=False))["enabled"] is False


# =========================================================================== 10c: feedback, one generation at a time, API
def test_feedback_is_saved_with_ticker_tab_language_and_version(tmp_store, monkeypatch):
    monkeypatch.setattr(service, "FEEDBACK_FILE", tmp_store / "fb.jsonl")
    service.save_feedback("aapl", "valuation", "id", "1.0", "down", source="fallback", surface="mobile")
    row = json.loads((tmp_store / "fb.jsonl").read_text(encoding="utf-8"))
    assert (row["ticker"], row["tab"], row["lang"], row["prompt_version"], row["vote"]) == ("AAPL", "valuation", "id", "1.0", "down")
    with pytest.raises(ValueError):
        service.save_feedback("AAPL", "valuation", "en", "1.0", "maybe")


def test_same_summary_is_generated_once_when_asked_twice_at_the_same_time(tmp_store):
    import threading
    import time as _t

    class SlowSDK(FakeSDK):
        def _parse(self, **kw):
            _t.sleep(0.3)
            return super()._parse(**kw)

    sdk = SlowSDK(GOOD, GOOD)
    outs = []
    th = [threading.Thread(target=lambda: outs.append(run(sdk))) for _ in range(2)]
    [t.start() for t in th]
    [t.join() for t in th]
    assert len(sdk.calls) == 1 and sorted(o["cached"] for o in outs) == [False, True]


def test_api_hides_the_card_when_ai_is_off_and_saves_feedback(tmp_store, monkeypatch):
    from fastapi.testclient import TestClient

    import api.main as api
    from config import settings as settings_mod

    monkeypatch.setattr(service, "FEEDBACK_FILE", tmp_store / "fb.jsonl")
    monkeypatch.setattr(api, "settings", Settings(anthropic_api_key="", ai_summaries_enabled=False))
    c = TestClient(api.app)
    r = c.get("/stocks/AAPL/ai-summary?tab=valuation&lang=id")
    assert r.status_code == 200 and r.json()["data"] == {"enabled": False}
    assert c.get("/ai/usage").json()["enabled"] is False
    ok = c.post("/ai-feedback", json={"ticker": "AAPL", "tab": "valuation", "lang": "id", "prompt_version": "1.0",
                                     "vote": "up", "surface": "mobile"})
    assert ok.json() == {"saved": True} and (tmp_store / "fb.jsonl").exists()
    assert c.post("/ai-feedback", json={"ticker": "AAPL", "tab": "nope", "lang": "id", "prompt_version": "1.0",
                                       "vote": "up"}).status_code == 422
    assert settings_mod   # imported only to make sure the real settings module is untouched


# =========================================================================== 10b round 2 fixes (prompt 2.1)
def test_sp500_is_a_name_not_a_number():
    assert check_numbers(make("Beat the S&P 500 by 39.5%."), PAYLOAD) == []
    assert check_numbers(make("Beat the S&P 500 by 41%."), PAYLOAD)          # other numbers are still checked


def test_named_firm_rating_changes_count_as_analyst_opinions():
    s = make("China Renaissance raised its rating from Hold to Buy.")
    assert check_banned(s, "ownership_sentiment") == []
    assert check_banned(make("Barclays menaikkan peringkat ke beli."), "ownership_sentiment") == []
    assert check_banned(s, "valuation")                                       # not outside the analyst tabs


@pytest.mark.parametrize("text", ["Ada tekanan jual di dekat resistance.", "Hasilnya belum pasti.",
                                  "Aksi jual di sektor teknologi.", "Arahnya tidak pasti."])
def test_ordinary_indonesian_phrases_are_allowed(text):
    assert check_banned(make(text), "price_technicals") == []


def test_allowed_phrases_do_not_hide_real_advice():
    assert check_banned(make("Ada tekanan jual, sebaiknya jual sekarang."), "price_technicals")


def test_too_thin_answer_is_retried_but_short_tabs_are_fine():
    from core.ai_summary.validator import check_completeness
    rich = {"metrics": [{"key": f"m{i}", "value": i + 2} for i in range(12)]}
    one = make(bullish=[pt("P/E is 39.5.", "Only one point")])
    assert check_completeness(one, rich)
    assert check_completeness(one, {"metrics": []}) == []                     # e.g. no dividend: little data
    assert check_completeness(make("P/E is 39.5.", bullish=[]), {}, strengths=["Margins are high."])
    assert check_completeness(make("P/E is 39.5.", bullish=[pt("x y")]), rich, strengths=["s"], risks=["r"]) == []


def test_license_tags_are_not_sent_to_the_model():
    ti = tab_input()
    assert "license_tag" in json.dumps(ti.payload)                            # still tracked in our code
    msg = user_message("valuation", "en", "USD", ti.payload)
    assert "license_tag" not in msg and "DEMO_ONLY" not in msg
