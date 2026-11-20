"""Load everything for one ticker in parallel. Used by the Streamlit app (and later the API).
Each part fails on its own: a failed source becomes None plus an entry in `errors`."""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from core.analysis import Analysis, load_analysis
from core.company import ResolvedTicker, load_header
from core.earnings_service import EarningsData, load_earnings
from core.extras_service import DividendData, NewsData, OwnershipData, load_dividends, load_news, load_ownership
from core.financials import Financials
from core.financials_service import load_financials
from core.logging_setup import get_logger
from core.models import HeaderData
from core.price_service import PriceAnalysis, load_price_analysis
from core.scorecard import Scorecard, build_facts, build_scorecard

log = get_logger("bundle")


@dataclass
class Bundle:
    resolved: ResolvedTicker
    header: HeaderData
    fin: Optional[Financials] = None
    analysis: Optional[Analysis] = None
    price: Optional[PriceAnalysis] = None
    earnings: Optional[EarningsData] = None
    dividends: Optional[DividendData] = None
    ownership: Optional[OwnershipData] = None
    news: Optional[NewsData] = None
    errors: dict[str, str] = field(default_factory=dict)
    seconds: float = 0.0

    def scorecard(self, lang: str = "en", safe_mode: bool = False) -> Optional[Scorecard]:
        if self.analysis is None and self.price is None:
            return None
        facts = build_facts(self.analysis, self.price, self.earnings, self.dividends, self.ownership)
        return build_scorecard(facts, lang=lang, safe_mode=safe_mode)


def _run(errors: dict[str, str], name: str, fn: Callable, *args) -> Any:
    try:
        return fn(*args)
    except Exception as exc:  # noqa: BLE001 - one part failing must not break the page
        log.exception("%s failed", name)
        errors[name] = f"{type(exc).__name__}: {exc}"
        return None


def load_bundle(resolved: ResolvedTicker) -> Bundle:
    start = time.perf_counter()
    errors: dict[str, str] = {}
    header = load_header(resolved)
    sym, cik = resolved.symbol, resolved.cik
    sector = header.profile.sector.value if header.profile.sector.available else None
    fin = _run(errors, "financials", load_financials, sym, cik, header.profile.is_financial_company)
    with ThreadPoolExecutor(max_workers=5) as pool:
        f_an = pool.submit(_run, errors, "ratios", load_analysis, sym, header, fin)
        f_px = pool.submit(_run, errors, "prices", load_price_analysis, sym, sector)
        f_er = pool.submit(_run, errors, "earnings", load_earnings, sym, cik, fin)
        f_ow = pool.submit(_run, errors, "ownership", load_ownership, sym)
        f_nw = pool.submit(_run, errors, "news", load_news, sym, cik)
        analysis = f_an.result()
        q = analysis.quarterly if analysis is not None else None
        f_dv = pool.submit(_run, errors, "dividends", load_dividends, sym, header.price.value, fin, q)
        b = Bundle(resolved=resolved, header=header, fin=fin, analysis=analysis, price=f_px.result(),
                   earnings=f_er.result(), dividends=f_dv.result(), ownership=f_ow.result(), news=f_nw.result(),
                   errors=errors)
    b.seconds = time.perf_counter() - start
    log.info("Loaded %s in %.1fs (errors: %s)", sym, b.seconds, list(errors) or "none")
    return b
