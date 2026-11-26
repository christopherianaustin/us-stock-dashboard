"""Phase 10b: generate AI summaries for every tab, test ticker and language, and save them for review.

Spends real money (about 100 calls, ~$5-7). Needs ANTHROPIC_API_KEY in .env.
Usage:  .venv\\Scripts\\python scripts/ai_samples.py [TICKER ...]      (default: AAPL KO TSLA JPM PLUG)
Output: core/ai_summary/samples/<TICKER>.md   (readable)   and   core/ai_summary/samples/_results.json (for checks)
"""
from __future__ import annotations

import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from api.main import ai_tab_input, get_bundle  # noqa: E402
from config.settings import settings  # noqa: E402
from core.ai_summary.client import tab_focus  # noqa: E402
from core.ai_summary.input_builder import TABS  # noqa: E402
from core.ai_summary.service import LOG_FILE, get_summary  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "core" / "ai_summary" / "samples"
LANGS = (("en", "USD"), ("id", "IDR"))


def one(ticker: str, tab: str, lang: str, cur: str) -> dict:
    _, ti = ai_tab_input(ticker, tab, lang, cur, settings.production_safe_mode)
    cur = cur if (cur == "USD" or "exchange_rate_used" in ti.payload) else "USD"
    t0 = time.time()
    res = get_summary(ticker, tab, lang, cur, ti, use_cache=False)
    return {"ticker": ticker, "tab": tab, "lang": lang, "currency": cur, "seconds": round(time.time() - t0, 1),
            "payload": ti.payload, "rule_strengths": ti.strengths, "rule_risks": ti.risks, **res}


def md_block(r: dict) -> list[str]:
    s, lines = r["summary"], []
    u = r.get("usage") or {}
    meta = (f"source **{r['source']}** · attempts {r.get('attempts', '-')} · rule signal {r['rule_based_signal']} · "
            f"license {r['license_tag']} · tokens {u.get('total', 0):,} · ${r.get('cost_usd') or 0:.4f} · {r['seconds']} s")
    lines.append(f"*{meta}*\n")
    if r["source"] == "fallback":
        lines.append(f"> AI not used: {r.get('reason')}\n")
        lines.append(f"**{s['label']}** · signal {s['signal']}\n")
        lines += [f"- ✅ {p}" for p in s["positives"]] + [f"- ⚠️ {p}" for p in s["watch_outs"]]
        return lines + [""]
    lines.append(f"**[{s['signal']}] {s['headline']}**\n")
    lines.append(f"{s['takeaway']}\n")
    for p in s["positives"]:
        lines.append(f"- ✅ {p['text']}  `{', '.join(p['metric_keys'])}`")
    for p in s["watch_outs"]:
        lines.append(f"- ⚠️ {p['text']}  `{', '.join(p['metric_keys'])}`")
    for w in s["what_to_watch_next"]:
        lines.append(f"- 📅 {w}")
    lines.append(f"- ❓ {s['ask_yourself']}")
    if s["data_gaps"]:
        lines.append(f"- Data gaps: {'; '.join(s['data_gaps'])}")
    return lines + [""]


def main() -> None:
    if not settings.ai_enabled:
        sys.exit("AI summaries are off: set ANTHROPIC_API_KEY in .env.")
    tickers = [t.upper() for t in sys.argv[1:]] or ["AAPL", "KO", "TSLA", "JPM", "PLUG"]
    OUT.mkdir(parents=True, exist_ok=True)
    for t in tickers:          # load each stock's data once, before the parallel calls
        get_bundle(t)
    log_start = LOG_FILE.stat().st_size if LOG_FILE.exists() else 0
    jobs = [(t, tab, lang, cur) for t in tickers for tab in TABS for lang, cur in LANGS]
    results: list[dict] = []
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=6) as pool:
        futs = {pool.submit(one, *j): j for j in jobs}
        for i, f in enumerate(as_completed(futs), 1):
            j = futs[f]
            try:
                r = f.result()
                results.append(r)
                print(f"[{i}/{len(jobs)}] {j[0]} {j[1]} {j[2]}: {r['source']} (attempts {r.get('attempts', '-')}, "
                      f"${r.get('cost_usd') or 0:.3f})", flush=True)
            except Exception as e:  # noqa: BLE001 - keep going, report at the end
                print(f"[{i}/{len(jobs)}] {j[0]} {j[1]} {j[2]}: ERROR {e}", flush=True)
                results.append({"ticker": j[0], "tab": j[1], "lang": j[2], "error": str(e)})

    order = {t: i for i, t in enumerate(TABS)}
    for t in tickers:
        rows = sorted([r for r in results if r["ticker"] == t and "error" not in r],
                      key=lambda r: (order[r["tab"]], r["lang"]))
        cost = sum(r.get("cost_usd") or 0 for r in rows)
        toks = sum((r.get("usage") or {}).get("total", 0) for r in rows)
        name = next((r["payload"].get("company") for r in rows if r["payload"].get("company")), t)
        lines = [f"# {t} · {name}: AI summary samples\n",
                 f"Prompt version {rows[0]['prompt_version'] if rows else '?'} · model {settings.ai_model} · effort "
                 f"{settings.ai_effort} · generated {time.strftime('%Y-%m-%d %H:%M')}  ",
                 f"Total for {len(rows)} summaries: **{toks:,} tokens, ${cost:.2f}**\n",
                 "AI-generated from our data. It can make mistakes and is not investment advice.\n"]
        for tab in TABS:
            lines.append(f"## {tab_focus()[tab]['name']}\n")
            for r in [r for r in rows if r["tab"] == tab]:
                lines.append(f"### {'English (USD)' if r['lang'] == 'en' else 'Bahasa Indonesia (' + r['currency'] + ')'}\n")
                lines += md_block(r)
        (OUT / f"{t}.md").write_text("\n".join(lines), encoding="utf-8")

    with open(LOG_FILE, encoding="utf-8") as f:
        f.seek(log_start)
        attempts_log = [json.loads(x) for x in f if x.strip()]
    (OUT / "_results.json").write_text(json.dumps({"results": results, "log": attempts_log}, ensure_ascii=False,
                                                  default=str, indent=1), encoding="utf-8")
    total = sum(r.get("cost_usd") or 0 for r in results)
    print(f"\nDone in {time.time() - t0:.0f} s. {len(results)} summaries, total ${total:.2f}. Files in {OUT}")


if __name__ == "__main__":
    main()
