"""Creates provider instances and applies the source priority rules (SPEC 4.5)."""
from __future__ import annotations

import functools
from typing import Optional

import pandas as pd

from config.settings import settings
from core.logging_setup import get_logger
from core.models import Quote
from core.providers.base import PriceProvider, ProviderError
from core.providers.finnhub_provider import FinnhubProvider
from core.providers.nanovest_price import NanovestPriceProvider
from core.providers.sec_edgar import SecEdgarClient
from core.providers.yfinance_provider import YFinanceProvider

log = get_logger("registry")


@functools.lru_cache(maxsize=1)
def sec() -> SecEdgarClient:
    return SecEdgarClient()


@functools.lru_cache(maxsize=1)
def yfinance() -> YFinanceProvider:
    return YFinanceProvider()


@functools.lru_cache(maxsize=1)
def finnhub() -> FinnhubProvider:
    return FinnhubProvider()


def price_providers() -> list[PriceProvider]:
    """Price priority: PRICE_PROVIDER first, then yfinance as fallback."""
    if settings.price_provider == "nanovest":
        return [NanovestPriceProvider(), yfinance()]
    return [yfinance()]


def get_quote(symbol: str) -> Optional[Quote]:
    for p in price_providers():
        try:
            q = p.get_quote(symbol)
            if q is not None:
                return q
        except ProviderError as exc:
            log.info("Price provider %s unavailable: %s", p.source.value, exc)
    return None


def get_history(symbol: str, period: str = "1y") -> tuple[Optional[pd.DataFrame], Optional[PriceProvider]]:
    """Daily history plus the provider it came from (for source/license badges)."""
    for p in price_providers():
        try:
            if isinstance(p, YFinanceProvider):
                df = p.get_history(symbol, period=period)
            else:
                years = int(period[:-1]) if period.endswith("y") and period[:-1].isdigit() else 1
                start = (pd.Timestamp.today() - pd.DateOffset(years=years)).date()
                df = p.get_history(symbol, start=start)
            if df is not None and not df.empty:
                return df, p
        except ProviderError as exc:
            log.info("Price provider %s unavailable: %s", p.source.value, exc)
    return None, None
