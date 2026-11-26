"""Step 10b review (prompt 2.0, SPEC 16.8): check every saved sample against the quality list. No API calls.

Checks per tab: nothing important missing, no repeated points, both sides considered, every number correct,
no banned words; plus lengths, plain language, missing-data handling and cost.
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
from core.ai_summary.validator import (check_banned, check_numbers, matches, numbers_in_text,  # noqa: E402
                                       sentences, words)

DATA = json.loads((Path(__file__).resolve().parent.parent / "core/ai_summary/samples/_results.json").read_text(encoding="utf-8"))
results = [r for r in DATA["results"] if "error" not in r]
log = DATA["log"]
ai = [r for r in results if r["source"] == "ai"]
SIDES = ("bullish", "bearish")


def pts(r: dict) -> list[dict]:
    return [p for k in SIDES for p in r["summary"][k]]


def all_text(r: dict) -> str:
    return " ".join(f"{p['title']}. {p['detail']}" for p in pts(r))


def nums(text: str) -> set[float]:
    out = set()
    for _, rs in numbers_in_text(text):
        out |= {x for x in rs if x not in (0.0, 1.0, 100.0)}
    return out


print(f"Summaries: {len(results)} ok, {len(DATA['results']) - len(results)} errors\n")

# ---- 1. sources, retries, failure reasons
src = Counter(r["source"] for r in results)
att = Counter(r.get("attempts") for r in ai)
print("1. Result:", dict(src), "| AI on attempt:", dict(att))
fails = Counter()
for e in log:
    for f in e.get("checks_failed") or []:
        fails[re.sub(r'(\[\d+\])|(".*)|(\d+ words.*)|(\d+ sentences.*)|(\d+ items.*)|(\d+ points.*)', "", f).strip()] += 1
    if e["result"] in ("error", "refused"):
        fails[e["result"] + ": " + e.get("error", "")[:60]] += 1
print("   check failures on any attempt:", dict(fails.most_common()))
for e in log:
    for f in e.get("checks_failed") or []:
        print(f"     - {e['ticker']} {e['tab']} {e['lang']} try {e['attempt']}: {f[:160]}")
for r in results:
    if r["source"] == "fallback":
        print(f"   FALLBACK {r['ticker']} {r['tab']} {r['lang']}: {str(r.get('reason'))[:160]}")

# ---- 2. every number correct, no banned words (re-checked on the final outputs)
bad_num = [(r, f) for r in ai for f in check_numbers(TabSummary.model_validate(r["summary"]), r["payload"])]
bad_word = [(r, f) for r in ai for f in check_banned(TabSummary.model_validate(r["summary"]), r["tab"])]
print(f"\n2. Final outputs: numbers not in data = {len(bad_num)}, banned phrases = {len(bad_word)}")
for r, f in bad_num + bad_word:
    print(f"     - {r['ticker']} {r['tab']} {r['lang']}: {f}")

# ---- 3. both sides considered
sizes = Counter((len(r["summary"]["bullish"]), len(r["summary"]["bearish"])) for r in ai)
print(f"\n3. Both sides: (bullish, bearish) counts: {dict(sorted(sizes.items()))}")
for r in ai:
    for side, rule in (("bullish", r["rule_strengths"]), ("bearish", r["rule_risks"])):
        if not r["summary"][side]:
            note = f"rule-based {side} points: {len(rule)}" + (" <-- CHECK" if rule else " (rule-based side also empty)")
            print(f"     - empty {side}: {r['ticker']} {r['tab']} {r['lang']} ({note})")

# ---- 4. nothing important missing: are the rule-based findings (Section 7) covered by the AI points?
print("\n4. Coverage of the rule-based findings (a finding counts as covered when its main number is in an AI point)")
cov_total = cov_hit = 0
missing = []
for r in ai:
    text_nums = nums(all_text(r))
    for kind, items in (("strength", r["rule_strengths"]), ("risk", r["rule_risks"])):
        for item in items[:4]:
            n = nums(item) - {8.0}                       # "8 of 8" style counts are too generic to match on
            if not n:
                continue
            cov_total += 1
            if any(matches(x, text_nums) for x in n):
                cov_hit += 1
            else:
                missing.append((r, kind, item))
print(f"   covered {cov_hit} of {cov_total} ({cov_hit / max(cov_total, 1):.0%}); not covered by number:")
for r, kind, item in missing:
    print(f"     - {r['ticker']} {r['tab']} {r['lang']} {kind}: {item}")

# ---- 5. no repeated points
print("\n5. Repeated points (same metric keys, or titles sharing most words)")


def tokens(t: str) -> set[str]:
    return {w for w in re.findall(r"[a-zA-Z/]+", t.lower()) if len(w) > 3}


BROAD = {"headlines", "returns_pct", "last_quarters", "analyst_estimate_revisions_30d", "recent_filings"}  # one key, many facts
reps = 0
for r in ai:
    ps = [(side, p) for side in SIDES for p in r["summary"][side]]
    for i in range(len(ps)):
        for j in range(i + 1, len(ps)):
            (sa, a), (sb, b) = ps[i], ps[j]
            same_keys = a["metric_keys"] and set(a["metric_keys"]) == set(b["metric_keys"])                 and not set(a["metric_keys"]) <= BROAD
            ta, tb = tokens(a["title"]), tokens(b["title"])
            close = ta and tb and len(ta & tb) / len(ta | tb) >= 0.5
            if same_keys or close:
                reps += 1
                print(f"     - {r['ticker']} {r['tab']} {r['lang']}: [{sa}] {a['title']} | [{sb}] {b['title']}"
                      f"  ({'same keys ' + str(a['metric_keys']) if same_keys else 'similar titles'})")
print(f"   possible repeats: {reps}")

# ---- 6. lengths and plain language
tw = [words(p["title"]) for r in ai for p in pts(r)]
dw = [words(p["detail"]) for r in ai for p in pts(r)]
print(f"\n6. Titles: {min(tw)}-{max(tw)} words (avg {sum(tw) / len(tw):.1f}); details: max {max(dw)}, avg "
      f"{sum(dw) / len(dw):.1f} words; points per card avg {len(tw) / len(ai):.1f}")
multi = [(r, p) for r in ai for p in pts(r) if len(sentences(p["detail"])) > 1]
print(f"   details with more than one sentence: {len(multi)}")
by_lang = defaultdict(list)
for r in ai:
    by_lang[r["lang"]] += [words(p["detail"]) for p in pts(r)]
print("   " + " | ".join(f"{k}: avg detail {sum(v) / len(v):.1f} words" for k, v in by_lang.items()))
jargon = Counter()
for r in ai:
    txt = all_text(r)
    for term in ("P/E", "EPS", "ROE", "ROIC", "EBITDA", "DCF", "PEG", "RSI", "beta", "Beta", "Piotroski", "Altman",
                 "free cash flow", "arus kas bebas", "short interest"):
        m = re.search(re.escape(term), txt)
        if m:
            explained = txt[m.end():m.end() + 3].lstrip().startswith("(") or "(" in txt[m.end():m.end() + 25][:3]
            jargon[(term, "explained" if explained else "bare")] += 1
print("   first use of finance terms:", {f"{t} {k}": n for (t, k), n in sorted(jargon.items())})
print(f"   exclamation marks: {sum('!' in all_text(r) for r in ai)}")
gap_demo = [r for r in ai if any(re.search(r"(?i)demo|lisensi|license", g) for g in r["summary"]["data_gaps"])]
print(f"   data_gaps mentioning demo/license tags: {len(gap_demo)} of {len(ai)}; cards with data_gaps: "
      f"{sum(bool(r['summary']['data_gaps']) for r in ai)}")

# ---- 7. missing data handling
print("\n7. Missing data")
for r in results:
    s = r["summary"]
    show = (r["ticker"] == "JPM" and r["tab"] in ("financials", "profitability_health")) or \
           (r["ticker"] == "TSLA" and r["tab"] == "dividends") or (r["ticker"] == "PLUG" and r["tab"] == "valuation")
    if not show:
        continue
    if r["source"] == "ai":
        body = " || ".join(f"[{k[:4]}] {p['title']}: {p['detail']}" for k in SIDES for p in s[k])
    else:
        body = "FALLBACK " + " || ".join(s["bullish"] + s["bearish"])
    print(f"   {r['ticker']} {r['tab']} {r['lang']}: {body[:600]}\n      gaps: {s.get('data_gaps')}")

# ---- 8. cost
print("\n8. Cost and tokens (all attempts)")
per_t = defaultdict(lambda: [0.0, 0])
per_tab = defaultdict(lambda: [0.0, 0])
for r in results:
    c, t = r.get("cost_usd") or 0, (r.get("usage") or {}).get("total", 0)
    per_t[r["ticker"]][0] += c
    per_t[r["ticker"]][1] += t
    per_tab[r["tab"]][0] += c
for k, (c, t) in per_t.items():
    print(f"   {k}: ${c:.2f} for 20 summaries ({t:,} tokens)")
n_t = len(per_t)
for k, (c, _) in per_tab.items():
    print(f"   {k}: avg ${c / (2 * n_t):.3f} per summary")
ok_logs = [e for e in log if e.get("usage")]
avg = lambda k: sum(e["usage"][k] for e in ok_logs) / len(ok_logs)  # noqa: E731
print(f"   per call average: input {avg('input'):.0f}, cache read {avg('cache_read'):.0f}, cache write "
      f"{avg('cache_write'):.0f}, output {avg('output'):.0f}  | total ${sum(r.get('cost_usd') or 0 for r in results):.2f}")
secs = [r["seconds"] for r in results]
print(f"   time per summary: avg {sum(secs) / len(secs):.0f} s, max {max(secs):.0f} s")
