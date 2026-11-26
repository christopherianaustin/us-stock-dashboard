"""Phase 10a demo: one real AI summary in English and Indonesian, with token count and cost.

Spends real money (about 2 API calls, more if a check fails and it retries). Needs ANTHROPIC_API_KEY in .env.
Usage:  .venv\\Scripts\\python scripts/ai_example.py [TICKER] [TAB]      (default: AAPL valuation)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from api.main import ai_tab_input  # noqa: E402
from config.settings import settings  # noqa: E402
from core.ai_summary.service import get_summary  # noqa: E402


def show(res: dict) -> None:
    s = res["summary"]
    print(f"source: {res['source']}   model: {res.get('model')}   attempts: {res.get('attempts', '-')}   "
          f"license: {res['license_tag']}   rule-based signal: {res['rule_based_signal']}")
    if res["source"] == "fallback":
        print(f"(AI not used: {res.get('reason')})")
        print(f"[{s['label']}] signal: {s['signal']}")
        for p in s["positives"]:
            print(f"  + {p}")
        for p in s["watch_outs"]:
            print(f"  ! {p}")
    else:
        print(f"[{s['signal']}] {s['headline']}")
        print(f"  {s['takeaway']}")
        for p in s["positives"]:
            print(f"  + {p['text']}   ({', '.join(p['metric_keys'])})")
        for p in s["watch_outs"]:
            print(f"  ! {p['text']}   ({', '.join(p['metric_keys'])})")
        for w in s["what_to_watch_next"]:
            print(f"  > {w}")
        print(f"  ? {s['ask_yourself']}")
        if s["data_gaps"]:
            print(f"  data gaps: {s['data_gaps']}")
    u = res.get("usage") or {}
    print(f"tokens: input {u.get('input', 0):,} + cache write {u.get('cache_write', 0):,} + cache read "
          f"{u.get('cache_read', 0):,} + output {u.get('output', 0):,} = {u.get('total', 0):,}   "
          f"cost: ${res.get('cost_usd') or 0:.4f}")


def main() -> None:
    ticker = (sys.argv[1] if len(sys.argv) > 1 else "AAPL").upper()
    tab = sys.argv[2] if len(sys.argv) > 2 else "valuation"
    if not settings.ai_enabled:
        sys.exit("AI summaries are off: set ANTHROPIC_API_KEY in .env (and AI_SUMMARIES_ENABLED is not false).")
    total = 0.0
    for lang, cur in (("en", "USD"), ("id", "IDR")):
        _, ti = ai_tab_input(ticker, tab, lang, cur, settings.production_safe_mode)
        cur = cur if (cur == "USD" or "exchange_rate_used" in ti.payload) else "USD"
        print(f"\n===== {ticker} · {tab} · {lang.upper()} ({cur}) =====")
        res = get_summary(ticker, tab, lang, cur, ti, use_cache=False)
        show(res)
        total += res.get("cost_usd") or 0
    print(f"\nTotal for both languages: ${total:.4f}  (details in logs/ai_summaries.jsonl)")


if __name__ == "__main__":
    main()
