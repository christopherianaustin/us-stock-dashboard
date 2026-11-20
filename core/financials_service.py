"""Loads financial statements with source priority: SEC EDGAR first, then yfinance.
Also cross-checks SEC against yfinance and logs differences above 2%."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from core.cache import cached
from core.financials import (Financials, add_derived, build_from_sec_facts, build_from_yfinance,
                             cross_check)
from core.logging_setup import get_logger
from core.models import Source
from core.providers import registry

log = get_logger("financials_service")

BUILD_VERSION = "v3"  # bump when the builder logic changes, to ignore old cached results


@cached(f"financials_{BUILD_VERSION}", "sec_companyfacts")
def load_financials(symbol: str, cik: Optional[str], is_financial: bool = False) -> Optional[Financials]:
    warnings: list[str] = []

    def _yf():
        try:
            return registry.yfinance().get_statements(symbol)
        except Exception as exc:  # noqa: BLE001
            log.warning("yfinance statements failed for %s: %s", symbol, exc)
            return None

    def _sec():
        return registry.sec().get_company_facts_by_cik(cik) if cik else None

    # Download the SEC facts and the yfinance backup tables at the same time
    with ThreadPoolExecutor(max_workers=2) as pool:
        f_yf, f_sec = pool.submit(_yf), pool.submit(_sec)
        yf_statements = f_yf.result()
    yf_tidy = build_from_yfinance(yf_statements) if yf_statements else None

    if cik:
        try:
            facts = f_sec.result()
            sec_tidy = build_from_sec_facts(facts)
            if not sec_tidy.empty:
                check = cross_check(sec_tidy, yf_tidy) if yf_tidy is not None and not yf_tidy.empty else None
                if check is not None and (check["status"] == "Differs > 2%").any():
                    warnings.append("Some SEC numbers differ from yfinance by more than 2% "
                                    "(see 'Data quality check' at the bottom of this tab).")
                return Financials(symbol=symbol, source=Source.SEC.value,
                                  tidy=add_derived(sec_tidy, is_financial), is_financial=is_financial,
                                  crosscheck=check, warnings=warnings)
            warnings.append("SEC EDGAR has no usable financial data for this company.")
        except Exception as exc:  # noqa: BLE001 - fall back instead of failing the tab
            log.warning("SEC financials failed for %s: %s", symbol, exc)
            warnings.append("SEC EDGAR financial data could not be loaded.")

    if yf_tidy is not None and not yf_tidy.empty:
        warnings.append("Showing yfinance financial data (demo only, fewer periods).")
        return Financials(symbol=symbol, source=Source.YFINANCE.value,
                          tidy=add_derived(yf_tidy, is_financial), is_financial=is_financial, warnings=warnings)
    return None
