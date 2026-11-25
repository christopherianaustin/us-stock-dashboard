"""Phase 8: API tests.
Offline unit tests for JSON cleaning and safe-mode redaction; live tests call every endpoint function directly
(FastAPI endpoints are plain functions) and check the JSON contract. Live:  pytest -m network"""
import json
from datetime import date

import numpy as np
import pandas as pd
import pytest
from fastapi import HTTPException

from api import main as api
from core.models import DataPoint, LicenseTag, Source


# ---------------------------------------------------------------- offline
def test_clean_makes_everything_json_safe():
    data = {"a": np.float64(1.5), "b": np.int64(3), "c": float("nan"), "d": pd.Timestamp("2026-01-02"),
            "e": pd.NaT, "f": date(2026, 1, 3), "g": [np.bool_(True), LicenseTag.DEMO_ONLY],
            "h": pd.DataFrame({"x": [1.0, None]})}
    out = api.clean(data)
    json.dumps(out)   # must not raise
    assert out["a"] == 1.5 and out["b"] == 3 and out["c"] is None and out["d"] == "2026-01-02"
    assert out["e"] is None and out["f"] == "2026-01-03" and out["g"] == [True, "DEMO_ONLY"]
    assert out["h"] == [{"x": 1.0}, {"x": None}]


def test_val_redacts_demo_only_in_safe_mode():
    demo = DataPoint(value=349.2, source=Source.YFINANCE, license_tag=LicenseTag.DEMO_ONLY)
    safe = DataPoint(value=0.25, source=Source.CALCULATED, license_tag=LicenseTag.CALCULATED_SAFE)
    assert api.val(demo, safe=False)["value"] == 349.2
    red = api.val(demo, safe=True)
    assert red["value"] is None and red["na_reason"] == api.SAFE_TEXT and red["license_tag"] == "DEMO_ONLY"
    assert api.val(safe, safe=True)["value"] == 0.25
    assert api.block([1, 2], "yfinance", "DEMO_ONLY", safe=True)["items"] == []
    assert api.raw(5, "yfinance", "DEMO_ONLY", safe=True)["value"] is None


def test_cors_allows_only_the_local_prototype():
    """Phase 9: the mobile prototype (Vite on port 5173 / 4173) may call the API from the browser; other sites may not."""
    import re
    mw = [m for m in api.app.user_middleware if m.cls.__name__ == "CORSMiddleware"]
    assert mw, "CORS middleware missing"
    rx = re.compile(mw[0].kwargs["allow_origin_regex"])
    for ok in ("http://127.0.0.1:5173", "http://localhost:4173", "http://192.168.1.20:5173"):
        assert rx.fullmatch(ok), ok
    for bad in ("https://evil.example", "http://127.0.0.1:8501", "http://example.com:5173"):
        assert not rx.fullmatch(bad), bad
    assert mw[0].kwargs["allow_methods"] == ["GET"]


def test_fx_rate_is_hidden_in_safe_mode(monkeypatch):
    api._fx.clear()
    api._fx["usdidr"] = (__import__("time").time(), {"rate": 18000.0, "as_of": pd.Timestamp("2026-11-25")})
    assert api.fx_usdidr(False)["value"] == 18000.0
    red = api.fx_usdidr(True)
    assert red["value"] is None and red["license_tag"] == "DEMO_ONLY"
    api._fx.clear()


# ---------------------------------------------------------------- live
def _calls(t: str, safe: bool):
    return {
        "summary": lambda: api.summary(t, safe, "en"),
        "financials": lambda: api.financials(t, safe, "quarterly", "income", 12),
        "financials_annual_balance": lambda: api.financials(t, safe, "annual", "balance", 5),
        "ratios": lambda: api.ratios(t, safe),
        "valuation": lambda: api.valuation(t, safe, None, 0.10, 0.025),
        "technicals": lambda: api.technicals(t, safe, "1y", "1y"),
        "earnings": lambda: api.earnings(t, safe),
        "dividends": lambda: api.dividends(t, safe),
        "ownership": lambda: api.ownership(t, safe),
        "news": lambda: api.news(t, safe, 30),
        "profile": lambda: api.profile(t, safe),
        "coverage": lambda: api.coverage(t, safe),
    }


def _demo_values(obj, path=""):
    """Paths where a DEMO_ONLY-tagged value or block still has content."""
    bad = []
    if isinstance(obj, dict):
        if obj.get("license_tag") == "DEMO_ONLY":
            if obj.get("value") not in (None, [], {}) or obj.get("items"):
                bad.append(path)
        for k, v in obj.items():
            if k != "fields":   # the coverage report lists license names on purpose
                bad += _demo_values(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            bad += _demo_values(v, f"{path}[{i}]")
    return bad


@pytest.mark.network
@pytest.mark.parametrize("ticker", ["AAPL", "JPM", "TSLA"])
def test_every_endpoint_returns_valid_json(ticker):
    for name, call in _calls(ticker, False).items():
        env = call()
        body = env.model_dump()
        json.dumps(body)
        assert body["ticker"] and body["disclaimer"] and isinstance(body["data"], dict), name


@pytest.mark.network
def test_values_carry_source_license_as_of():
    d = api.summary("AAPL", False, "en").model_dump()["data"]
    for k in ("price", "market_cap", "name"):
        v = d["header"][k]
        assert v["source"] and v["license_tag"] and "as_of" in v
    rows = api.financials("AAPL", False, "quarterly", "income", 4).model_dump()["data"]["rows"]
    assert rows and all(r["source"] and r["license_tag"] and r["as_of"] for r in rows)


@pytest.mark.network
@pytest.mark.parametrize("ticker", ["AAPL", "JPM"])
def test_safe_mode_hides_every_demo_value(ticker):
    for name, call in _calls(ticker, True).items():
        body = call().model_dump()
        assert body["production_safe_mode"] is True
        bad = _demo_values(body["data"])
        assert not bad, f"{name}: {bad[:5]}"


@pytest.mark.network
def test_safe_mode_keeps_licensed_values():
    d = api.ratios("AAPL", True).model_dump()["data"]
    assert d["roe"]["value"] is not None and d["roe"]["license_tag"] == "CALCULATED_SAFE"
    assert d["pe"]["value"] is None and d["pe"]["na_reason"] == api.SAFE_TEXT


@pytest.mark.network
def test_invalid_ticker_is_404():
    with pytest.raises(HTTPException) as exc:
        api.summary("ZZZZQ", False, "en")
    assert exc.value.status_code == 404 and "ticker" in exc.value.detail.lower()


@pytest.mark.network
def test_no_dividend_message():
    d = api.dividends("TSLA", False).model_dump()["data"]
    assert d == {"pays_dividend": False, "message": "This company does not pay a dividend."}
