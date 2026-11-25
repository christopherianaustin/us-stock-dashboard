"""Save real API answers as the mobile prototype's offline "mock data mode" (SPEC 14.3).

Calls the FastAPI endpoint functions directly (no server needed) and writes one JSON file per endpoint:
    mobile-ui/public/mock/<TICKER>/<name>.json
Also exports the EN / ID glossary to mobile-ui/src/i18n/ so the prototype uses the same explanations.

Run from the project root (needs internet):   .venv/Scripts/python scripts/make_mobile_mocks.py [TICKERS...]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml
from fastapi import HTTPException

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from api import main as api  # noqa: E402

OUT = ROOT / "mobile-ui" / "public" / "mock"
I18N = ROOT / "mobile-ui" / "src" / "i18n"
TICKERS = sys.argv[1:] or ["AAPL", "KO", "TSLA", "JPM"]

# Columns the Technicals tab uses (the full API answer has more; trimmed to keep the files small).
BAR_COLS = {"date", "Open", "High", "Low", "Close", "Volume", "sma20", "sma50", "sma200", "rsi14",
            "macd", "signal", "hist"}


def calls(t: str) -> dict:
    c = {
        "summary": lambda: api.summary(t, False, "en"),
        "summary_id": lambda: api.summary(t, False, "id"),
        "ratios": lambda: api.ratios(t, False),
        "valuation": lambda: api.valuation(t, False, None, 0.10, 0.025),
        "technicals": lambda: api.technicals(t, False, "5y", "1y"),
        "earnings": lambda: api.earnings(t, False),
        "dividends": lambda: api.dividends(t, False),
        "ownership": lambda: api.ownership(t, False),
        "news": lambda: api.news(t, False, 30),
        "profile": lambda: api.profile(t, False),
    }
    for period, n in (("quarterly", 12), ("annual", 6)):
        for st in ("income", "balance", "cashflow"):
            c[f"financials_{period}_{st}"] = (lambda p=period, s=st, k=n: api.financials(t, False, p, s, k))
    return c


def trim(name: str, data: dict) -> dict:
    if name == "technicals":
        bars = data["data"]["bars"]
        bars["items"] = [{k: v for k, v in r.items() if k in BAR_COLS} for r in bars["items"]]
    if name == "ownership":
        it = data["data"]["insider_transactions"]
        it["items"] = it["items"][:30]
    if name == "news":
        data["data"]["sec_filings"]["items"] = data["data"]["sec_filings"]["items"][:30]
    return data


def main() -> None:
    for t in TICKERS:
        folder = OUT / t
        folder.mkdir(parents=True, exist_ok=True)
        for name, fn in calls(t).items():
            try:
                data = trim(name, fn().model_dump())
            except HTTPException as exc:
                data = {"error": exc.detail, "status": exc.status_code}
            (folder / f"{name}.json").write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")),
                                                 encoding="utf-8")
        print(t, "saved", sum(f.stat().st_size for f in folder.glob("*.json")) // 1024, "KB")
    fx = api.fx_usdidr(False)
    (OUT / "fx.json").write_text(json.dumps(fx, default=str), encoding="utf-8")
    print("fx", fx["value"])

    I18N.mkdir(parents=True, exist_ok=True)
    for lang in ("en", "id"):
        g = yaml.safe_load((ROOT / "config" / f"glossary_{lang}.yaml").read_text(encoding="utf-8"))
        (I18N / f"glossary_{lang}.json").write_text(json.dumps(g, ensure_ascii=False, indent=1), encoding="utf-8")
    print("glossary exported")


if __name__ == "__main__":
    main()
