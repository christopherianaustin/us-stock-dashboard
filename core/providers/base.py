"""Abstract provider interfaces.

The rest of the app only talks to these interfaces, so a demo source
(yfinance, Finnhub free) can later be swapped for a licensed vendor by writing
one new class. Methods for later phases are declared now so the contract is
visible; providers that don't support one simply don't implement that interface.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date
from typing import Any, Optional

import pandas as pd

from core.models import LicenseTag, Quote, Source


class ProviderError(Exception):
    """A provider could not return data (network error, rate limit, not found...)."""


class BaseProvider(ABC):
    source: Source
    license_tag: LicenseTag


class PriceProvider(BaseProvider):
    @abstractmethod
    def get_quote(self, symbol: str) -> Quote:
        """Latest price and today's change."""

    @abstractmethod
    def get_history(self, symbol: str, start: Optional[date] = None, end: Optional[date] = None,
                    interval: str = "1d") -> pd.DataFrame:
        """OHLCV history. Columns: Open, High, Low, Close, Volume; DatetimeIndex."""


class ProfileProvider(BaseProvider):
    @abstractmethod
    def get_profile(self, symbol: str) -> dict[str, Any]:
        """Raw company profile fields (name, sector, website...)."""


class FundamentalsProvider(BaseProvider):
    @abstractmethod
    def get_company_facts(self, symbol: str) -> dict[str, Any]:
        """All reported financial facts (Phase 2 turns these into statements)."""


class EstimatesProvider(BaseProvider):
    """Phase 5: earnings dates, surprises, analyst estimates."""

    @abstractmethod
    def get_next_earnings_date(self, symbol: str) -> Optional[date]:
        ...


class NewsProvider(BaseProvider):
    """Phase 6: company news."""

    @abstractmethod
    def get_news(self, symbol: str, days: int = 30) -> list[dict[str, Any]]:
        ...


class OwnershipProvider(BaseProvider):
    """Phase 6: holders and insider transactions."""

    @abstractmethod
    def get_major_holders(self, symbol: str) -> Any:
        ...
