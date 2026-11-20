"""Nanovest internal price feed (license tag: COMMERCIAL_OK) - STUB.

When Nanovest's price API is ready, fill in the two TODOs below and set
PRICE_PROVIDER="nanovest" in .env. Nothing else in the app needs to change.
Until then, these methods raise ProviderError and the app falls back to yfinance.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

import pandas as pd

from core.models import LicenseTag, Quote, Source
from core.providers.base import PriceProvider, ProviderError


class NanovestPriceProvider(PriceProvider):
    source = Source.NANOVEST
    license_tag = LicenseTag.COMMERCIAL_OK

    def __init__(self, base_url: Optional[str] = None, api_key: Optional[str] = None):
        # TODO: read NANOVEST_PRICE_API_URL / NANOVEST_PRICE_API_KEY from settings
        self.base_url = base_url
        self.api_key = api_key

    def get_quote(self, symbol: str) -> Quote:
        # TODO: call Nanovest's real-time quote endpoint and map it to Quote:
        #   Quote(symbol=symbol, price=..., previous_close=..., change=..., change_pct=...,
        #         currency="USD", as_of=<timestamp>, source=self.source, license_tag=self.license_tag)
        raise ProviderError("Nanovest price feed not connected yet (stub)")

    def get_history(self, symbol: str, start: Optional[date] = None, end: Optional[date] = None,
                    interval: str = "1d") -> pd.DataFrame:
        # TODO: call Nanovest's historical bars endpoint and return a DataFrame with a
        #   DatetimeIndex and columns: Open, High, Low, Close, Volume (split-adjusted).
        raise ProviderError("Nanovest price feed not connected yet (stub)")
