"""Finnhub free API client (license tag: DEMO_ONLY).

Free tier allows about 60 calls/minute. If FINNHUB_API_KEY is empty, every
method returns None and the app falls back to other sources.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from typing import Any, Optional

import requests

from config.settings import settings
from core.cache import cached
from core.logging_setup import get_logger, log_call
from core.models import LicenseTag, Source
from core.providers.base import ProfileProvider, ProviderError
from core.symbols import for_finnhub

log = get_logger("finnhub")
BASE_URL = "https://finnhub.io/api/v1"


class _MinuteLimiter:
    def __init__(self, per_minute: int):
        self.per_minute = per_minute
        self.calls: deque[float] = deque()
        self._lock = threading.Lock()

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            while self.calls and now - self.calls[0] > 60:
                self.calls.popleft()
            if len(self.calls) >= self.per_minute:
                time.sleep(60 - (now - self.calls[0]) + 0.05)
            self.calls.append(time.monotonic())


_limiter = _MinuteLimiter(per_minute=55)


class FinnhubProvider(ProfileProvider):
    source = Source.FINNHUB
    license_tag = LicenseTag.DEMO_ONLY

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key if api_key is not None else settings.finnhub_api_key
        self.session = requests.Session()

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def _get(self, path: str, params: dict[str, Any], what: str) -> Any:
        if not self.enabled:
            return None
        _limiter.wait()
        try:
            with log_call("Finnhub", what):
                r = self.session.get(f"{BASE_URL}{path}", params={**params, "token": self.api_key}, timeout=15)
                if r.status_code in (401, 403):
                    raise ProviderError(f"Finnhub refused access ({r.status_code}); check FINNHUB_API_KEY or plan limits")
                if r.status_code == 429:
                    raise ProviderError("Finnhub rate limit reached; try again in a minute")
                r.raise_for_status()
                return r.json()
        except Exception as exc:  # noqa: BLE001
            log.warning("Finnhub %s failed: %s", what, exc)
            return None

    @cached("fh_profile2", "profile", method=True)
    def get_profile(self, symbol: str) -> Optional[dict[str, Any]]:
        data = self._get("/stock/profile2", {"symbol": for_finnhub(symbol)}, f"profile2 {symbol}")
        return data or None  # Finnhub returns {} for unknown symbols

    @cached("fh_next_earnings", "estimates", method=True)
    def get_next_earnings_date(self, symbol: str) -> Optional[str]:
        """Next earnings date (YYYY-MM-DD) within the next 120 days, from /calendar/earnings."""
        from datetime import date, timedelta
        today = date.today()
        data = self._get("/calendar/earnings",
                         {"symbol": for_finnhub(symbol), "from": today.isoformat(),
                          "to": (today + timedelta(days=120)).isoformat()},
                         f"calendar/earnings {symbol}")
        rows = (data or {}).get("earningsCalendar") or []
        dates = sorted(r["date"] for r in rows if r.get("date") and r["date"] >= today.isoformat())
        return dates[0] if dates else None

    @cached("fh_earnings", "estimates", method=True)
    def get_earnings_surprises(self, symbol: str) -> Optional[list[dict]]:
        """/stock/earnings: last quarters with actual, estimate, surprisePercent, period (free tier: ~4)."""
        data = self._get("/stock/earnings", {"symbol": for_finnhub(symbol)}, f"earnings {symbol}")
        return data if isinstance(data, list) and data else None

    @cached("fh_earn_calendar", "estimates", method=True)
    def get_earnings_calendar(self, symbol: str, days_back: int = 400, days_ahead: int = 120) -> Optional[list[dict]]:
        """/calendar/earnings rows (date, hour bmo/amc, epsEstimate/Actual, revenueEstimate/Actual)."""
        from datetime import date, timedelta
        today = date.today()
        data = self._get("/calendar/earnings",
                         {"symbol": for_finnhub(symbol), "from": (today - timedelta(days=days_back)).isoformat(),
                          "to": (today + timedelta(days=days_ahead)).isoformat()},
                         f"calendar/earnings range {symbol}")
        rows = (data or {}).get("earningsCalendar") or []
        return rows or None

    @cached("fh_company_news", "news", method=True)
    def get_company_news(self, symbol: str, days: int = 30) -> Optional[list[dict]]:
        """/company-news for the last `days` days (headline, source, url, image, datetime, summary)."""
        from datetime import date, timedelta
        today = date.today()
        data = self._get("/company-news", {"symbol": for_finnhub(symbol),
                                           "from": (today - timedelta(days=days)).isoformat(), "to": today.isoformat()},
                         f"company-news {symbol}")
        return data if isinstance(data, list) and data else None

    @cached("fh_recommendation", "estimates", method=True)
    def get_recommendation_trends(self, symbol: str) -> Optional[list[dict]]:
        """/stock/recommendation: monthly counts of strongBuy, buy, hold, sell, strongSell (period = month)."""
        data = self._get("/stock/recommendation", {"symbol": for_finnhub(symbol)}, f"recommendation {symbol}")
        return data if isinstance(data, list) and data else None

    @cached("fh_peers", "profile", method=True)
    def get_peers(self, symbol: str) -> Optional[list[str]]:
        data = self._get("/stock/peers", {"symbol": for_finnhub(symbol)}, f"peers {symbol}")
        if not isinstance(data, list):
            return None
        me = for_finnhub(symbol)
        peers = [p for p in data if isinstance(p, str) and p.upper() != me]
        return peers or None
