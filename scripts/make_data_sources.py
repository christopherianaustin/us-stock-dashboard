"""Generate DATA_SOURCES.md from the field catalog in core/coverage.py.

Run:  .venv\\Scripts\\python scripts/make_data_sources.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.coverage import CATALOG  # noqa: E402

BADGE = {"COMMERCIAL_OK": "🟢 COMMERCIAL_OK", "CALCULATED_SAFE": "🔵 CALCULATED_SAFE", "DEMO_ONLY": "🟠 DEMO_ONLY"}

HEADER = """# Data sources

Every field the dashboard shows, where it comes from, whether it may be used commercially, and what could replace it
in production. **Generated from `core/coverage.py`** (run `python scripts/make_data_sources.py`), the same catalog that
powers the in-app *Data Coverage* tab and the `GET /coverage/{ticker}` API endpoint.

## License tags

| Tag | Meaning |
|---|---|
| 🟢 COMMERCIAL_OK | From SEC EDGAR or the Nanovest price feed. OK for commercial use. |
| 🔵 CALCULATED_SAFE | Calculated by us only from COMMERCIAL_OK inputs. OK for commercial use. |
| 🟠 DEMO_ONLY | From yfinance or Finnhub's free tier, or calculated using them. **Demo only**: replace before launch. |

With `PRODUCTION_SAFE_MODE=true` every DEMO_ONLY item is hidden and shows "Requires a licensed data provider".

## Biggest wins when going to production

1. **Connect the Nanovest price feed** (`core/providers/nanovest_price.py`, then `PRICE_PROVIDER=nanovest`).
   Every price-based ratio, technical indicator, risk metric and the valuation history turn into CALCULATED_SAFE
   automatically, because they are calculated from SEC data plus the price.
2. **Parse SEC 13F and Form 4 filings directly** (free, licensed-safe) for institutional holders and insider trades.
3. **License one estimates vendor** (EPS / revenue estimates, revisions, earnings calendar, analyst ratings and price
   targets): this replaces the whole Earnings tab's demo data and parts of Valuation and Ownership.
4. **License a news feed and a corporate-actions feed** (dividends, splits, ex-dates).
5. **Risk-free rate**: switch `^IRX` to the US Treasury's daily rates (public domain).

## All fields
"""


def main() -> None:
    lines = [HEADER]
    section = None
    for f in CATALOG:
        if f.section != section:
            section = f.section
            lines.append(f"\n### {section}\n")
            lines.append("| Field | Source | License | Where it comes from | Production replacement |")
            lines.append("|---|---|---|---|---|")
        repl = "already licensed-safe" if f.replacement == "-" else f.replacement
        lines.append(f"| {f.field} | {f.source} | {BADGE[f.license]} | `{f.where}` | {repl} |")
    counts = {tag: sum(f.license == tag for f in CATALOG) for tag in BADGE}
    lines.append(f"\n---\n{len(CATALOG)} fields: " + ", ".join(f"{n} {t}" for t, n in counts.items()) + ".\n")
    (ROOT / "DATA_SOURCES.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote DATA_SOURCES.md ({len(CATALOG)} fields)")


if __name__ == "__main__":
    main()
