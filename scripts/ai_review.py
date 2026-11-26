"""Phase 10b review: check every saved sample against the quality list (SPEC 15.10 step 10b). No API calls.
Usage:  .venv\\Scripts\\python scripts/ai_review.py      (reads core/ai_summary/samples/_results.json)
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from core.ai_summary.schema import TabSummary  # noqa: E402
from core.ai_summary.validator import check_banned, check_numbers, sentences, words  # noqa: E402

DATA = json.loads((Path(__file__).resolve().parent.parent / "core/ai_summary/samples/_results.json").read_text(encoding="utf-8"))
results = [r for r in DATA["results"] if "error" not in r]
log = DATA["log"]


def all_text(s: dict) -> list[str]:
    return ([s["headline"], s["takeaway"], s["ask_yourself"]] + [p["text"] for p in s["positives"] + s["watch_outs"]]
            + s["what_to_watch_next"])


print(f"Summaries: {len(results)} ok, {len(DATA['results']) - len(results)} errors\n")

# ---- 1. sources, retries, failure reasons
src = Counter(r["source"] for r in results)
att = Counter(r.get("attempts") for r in results if r["source"] == "ai")
print("1. Result:", dict(src), "| AI on attempt:", dict(att))
fails = Counter()
for e in log:
    for f in e.get("checks_failed") or []:
        kind = re.sub(r'".*', "", f).strip()
        fails[kind] += 1
    if e["result"] in ("error", "refused"):
        fails[e["result"] + ": " + e.get("error", "")[:60]] += 1
print("   check failures on any attempt:", dict(fails.most_common()))
for e in log:
    for f in e.get("checks_failed") or []:
        print(f"     - {e['ticker']} {e['tab']} {e['lang']} try {e['attempt']}: {f[:150]}")
for r in results:
    if r["source"] == "fallback":
        print(f"   FALLBACK {r['ticker']} {r['tab']} {r['lang']}: {r.get('reason')}")

ai = [r for r in results if r["source"] == "ai"]

# ---- 2. re-check numbers and banned words on the final outputs (belt and braces)
bad_num = [(r, f) for r in ai for f in check_numbers(TabSummary.model_validate(r["summary"]), r["payload"])]
bad_word = [(r, f) for r in ai for f in check_banned(TabSummary.model_validate(r["summary"]), r["tab"])]
print(f"\n2. Final outputs: numbers not in data = {len(bad_num)}, banned phrases = {len(bad_word)}")

# ---- 3. headline length
hl = [words(r["summary"]["headline"]) for r in ai]
print(f"\n3. Headline words: max {max(hl)}, average {sum(hl) / len(hl):.1f}; over 12: {sum(h > 12 for h in hl)}")

# ---- 4. balance: watch-outs present when the rule-based scorecard found risks
missing_watch = [r for r in ai if r["rule_risks"] and not r["summary"]["watch_outs"]]
no_watch_any = [r for r in ai if not r["summary"]["watch_outs"] and r["tab"] not in ("company_profile",)]
print(f"\n4. Balance: rule-based risks but no watch-out = {len(missing_watch)}; no watch-outs at all (excl. profile) = {len(no_watch_any)}")
for r in no_watch_any:
    print(f"     - {r['ticker']} {r['tab']} {r['lang']}: rule risks {len(r['rule_risks'])}")
pos_neg = Counter((len(r["summary"]["positives"]), len(r["summary"]["watch_outs"])) for r in ai)
print("   (positives, watch-outs) counts:", dict(sorted(pos_neg.items())))

# ---- 5. plain language
long_sent, all_sent = [], 0
for r in ai:
    for t in all_text(r["summary"]):
        for s in sentences(t):
            all_sent += 1
            if words(s) > 20:
                long_sent.append((r, s))
by_lang = defaultdict(list)
for r in ai:
    for t in all_text(r["summary"]):
        by_lang[r["lang"]] += [words(s) for s in sentences(t)]
print(f"\n5. Plain language: sentences over 20 words = {len(long_sent)} of {all_sent} "
      + " | ".join(f"{k}: avg {sum(v) / len(v):.1f} words" for k, v in by_lang.items()))
jargon = Counter()
for r in ai:
    txt = " ".join(all_text(r["summary"]))
    for term in ("P/E", "EPS", "ROE", "ROIC", "EBITDA", "DCF", "PEG", "RSI", "beta", "Piotroski", "Altman", "free cash flow", "arus kas bebas"):
        for m in re.finditer(re.escape(term), txt):
            explained = txt[m.end():m.end() + 3].lstrip().startswith("(")
            jargon[(term, "explained" if explained else "bare")] += 1
print("   finance terms (first use should be explained in brackets):",
      {f"{t} {k}": n for (t, k), n in sorted(jargon.items())})
hype = [r for r in ai if re.search(r"!", " ".join(all_text(r["summary"])))]
print(f"   exclamation marks: {len(hype)}")
gap_demo = [r for r in ai if any(re.search(r"(?i)demo", g) for g in r["summary"]["data_gaps"])]
print(f"   data_gaps mentioning 'demo' license tags: {len(gap_demo)} of {len(ai)}")

# ---- 6. missing data handling
print("\n6. Missing data")
for r in results:
    s = r["summary"]
    if r["ticker"] == "JPM" and r["tab"] in ("financials", "profitability_health"):
        txt = " ".join(all_text(s) if r["source"] == "ai" else s["positives"] + s["watch_outs"])
        print(f"   JPM {r['tab']} {r['lang']}: mentions gross margin/profit: {bool(re.search(r'(?i)gross|kotor', txt))} | "
              f"data_gaps: {s.get('data_gaps')}")
    if r["ticker"] == "TSLA" and r["tab"] == "dividends":
        print(f"   TSLA dividends {r['lang']}: [{s.get('signal')}] {s.get('headline')} | {s.get('takeaway', '')[:160]}")
    if r["ticker"] == "PLUG" and r["tab"] == "valuation":
        print(f"   PLUG valuation {r['lang']}: [{s.get('signal')}] {s.get('headline')} | gaps: {s.get('data_gaps')}")

# ---- 7. signals vs rule
moved = [(r["ticker"], r["tab"], r["lang"], r["rule_based_signal"], r["summary"]["signal"]) for r in ai
         if r["summary"]["signal"] != r["rule_based_signal"]]
print(f"\n7. Signal moved from the rule-based one: {len(moved)}")
for m in moved:
    print("     -", *m)
en_id = defaultdict(dict)
for r in ai:
    en_id[(r["ticker"], r["tab"])][r["lang"]] = r["summary"]["signal"]
diff = [(k, v) for k, v in en_id.items() if len(v) == 2 and v["en"] != v["id"]]
print(f"   EN and ID disagree on the signal: {len(diff)}", diff)

# ---- 8. cost
print("\n8. Cost and tokens (all attempts)")
per_t = defaultdict(lambda: [0.0, 0])
per_tab = defaultdict(lambda: [0.0, 0])
for r in results:
    c, t = r.get("cost_usd") or 0, (r.get("usage") or {}).get("total", 0)
    per_t[r["ticker"]][0] += c; per_t[r["ticker"]][1] += t
    per_tab[r["tab"]][0] += c; per_tab[r["tab"]][1] += t
for k, (c, t) in per_t.items():
    print(f"   {k}: ${c:.2f} for 20 summaries ({t:,} tokens)")
n_t = len(per_t)
for k, (c, t) in per_tab.items():
    print(f"   {k}: avg ${c / (2 * n_t):.3f} per summary")
ok_logs = [e for e in log if e.get("usage")]
avg = lambda k: sum(e["usage"][k] for e in ok_logs) / len(ok_logs)  # noqa: E731
print(f"   per call average: input {avg('input'):.0f}, cache read {avg('cache_read'):.0f}, cache write {avg('cache_write'):.0f}, "
      f"output {avg('output'):.0f}  | total ${sum(r.get('cost_usd') or 0 for r in results):.2f}")
secs = [r["seconds"] for r in results]
print(f"   time per summary: avg {sum(secs) / len(secs):.0f} s, max {max(secs):.0f} s")
