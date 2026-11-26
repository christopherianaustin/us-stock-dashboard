"""Save the step 10b AI samples as "saved data" for the mobile prototype, so its AI Insight cards also work
without the API (mock data mode). No API calls, no cost.

Reads  core/ai_summary/samples/_results.json   (made by scripts/ai_samples.py)
Writes mobile-ui/public/mock/<TICKER>/ai_<tab>_<lang>.json   (same shape as GET /stocks/{ticker}/ai-summary)
Usage: .venv\\Scripts\\python scripts/make_ai_mocks.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "core/ai_summary/samples/_results.json"
OUT = ROOT / "mobile-ui/public/mock"
KEEP = ("enabled", "ticker", "tab", "lang", "prompt_version", "license_tag", "rule_based_signal", "as_of", "source",
        "summary", "model", "attempts", "cost_usd", "cached")
DISCLAIMER = {"en": "AI-generated from the data on this page. It can make mistakes and is not investment advice.",
              "id": "Dibuat oleh AI dari data di halaman ini. Bisa keliru dan bukan saran investasi."}


def main() -> None:
    results = json.loads(SRC.read_text(encoding="utf-8"))["results"]
    tickers = {p.name for p in OUT.iterdir() if p.is_dir()}       # only stocks that already have saved data
    n = 0
    for r in results:
        if "error" in r or r["ticker"] not in tickers:
            continue
        data = {k: r[k] for k in KEEP if k in r} | {"disclaimer": DISCLAIMER[r["lang"]], "sample": True}
        env = {"ticker": r["ticker"], "generated_at": r.get("as_of") or "", "production_safe_mode": False,
               "disclaimer": "This information is for educational purposes only and is not investment advice.",
               "warnings": [], "data": data}
        (OUT / r["ticker"] / f"ai_{r['tab']}_{r['lang']}.json").write_text(
            json.dumps(env, ensure_ascii=False, indent=1), encoding="utf-8")
        n += 1
    print(f"Wrote {n} saved AI answers for {', '.join(sorted(tickers))}")


if __name__ == "__main__":
    sys.exit(main())
