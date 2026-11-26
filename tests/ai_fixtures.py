"""Shared test data for the AI summary tests: the saved API answers in mobile-ui/public/mock/ (no network)."""
from __future__ import annotations

import json
from pathlib import Path

MOCK = Path(__file__).resolve().parent.parent / "mobile-ui" / "public" / "mock"
FILES = {
    "summary": "summary", "ratios": "ratios", "valuation": "valuation", "technicals": "technicals",
    "earnings": "earnings", "dividends": "dividends", "ownership": "ownership", "news": "news", "profile": "profile",
    "fin_q_income": "financials_quarterly_income", "fin_q_cashflow": "financials_quarterly_cashflow",
    "fin_q_balance": "financials_quarterly_balance", "fin_a_income": "financials_annual_income",
}


def sections(ticker: str) -> dict:
    out = {}
    for name, f in FILES.items():
        p = MOCK / ticker / f"{f}.json"
        env = json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
        out[name] = None if env is None or "data" not in env else env["data"]
    return out


def pillars(ticker: str) -> dict:
    sc = sections(ticker)["summary"]["scorecard"]
    return {p["pillar"]: {"score": p["score"], "level": p["level"]} for p in sc}


INSIGHTS = [
    {"kind": "strength", "pillar": "valuation", "text": "Free cash flow yield is 3.4%."},
    {"kind": "risk", "pillar": "valuation", "text": "P/E is higher than 96% of the last 5 years."},
    {"kind": "risk", "pillar": "momentum", "text": "Price is 2.5% below its 200-day average."},
]
