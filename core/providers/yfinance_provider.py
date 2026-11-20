"""yfinance provider (license tag: DEMO_ONLY).

yfinance is unofficial and can break or rate-limit, so every call retries with
backoff, is cached, and returns None/empty on failure instead of crashing.
Verified against yfinance 1.8.0.
"""
from __future__ import annotations

import time
from datetime import date, datetime, timezone
from typing import Any, Callable, Optional

import pandas as pd
import yfinance as yf

from core.cache import cached
from core.logging_setup import get_logger, log_call
from core.models import LicenseTag, Quote, Source
from core.providers.base import EstimatesProvider, PriceProvider, ProfileProvider, ProviderError
from core.symbols import for_yfinance

log = get_logger("yfinance")


def _retry(func: Callable, what: str, attempts: int = 3, base_delay: float = 1.0):
    """Run func with retry + exponential backoff; logs each attempt."""
    last_exc: Exception | None = None
    for i in range(attempts):
        try:
            with log_call("yfinance", what):
                return func()
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            msg = str(exc).lower()
            # Not-found errors won't fix themselves; don't retry
            if "not found" in msg or "delisted" in msg or "404" in msg:
                break
            if i < attempts - 1:
                time.sleep(base_delay * (2 ** i))
    raise ProviderError(f"yfinance {what} failed: {last_exc}")


class YFinanceProvider(PriceProvider, ProfileProvider, EstimatesProvider):
    source = Source.YFINANCE
    license_tag = LicenseTag.DEMO_ONLY

    # ---------- prices ----------
    @cached("yf_history", "price_history", method=True)
    def get_history(self, symbol: str, start: Optional[date] = None, end: Optional[date] = None,
                    interval: str = "1d", period: Optional[str] = None) -> Optional[pd.DataFrame]:
        """Daily OHLCV. Uses `period` (e.g. '1y', '5y') if start is not given."""
        t = yf.Ticker(for_yfinance(symbol))

        def call():
            if start is not None:
                return t.history(start=start, end=end, interval=interval, auto_adjust=False)
            return t.history(period=period or "1y", interval=interval, auto_adjust=False)

        try:
            df = _retry(call, f"history {symbol} {period or start} {interval}")
        except ProviderError as exc:
            log.warning("%s", exc)
            return None
        if df is None or df.empty:
            return None
        return df

    @cached("yf_history_raw", "price_history", tag_arg=None, method=True)
    def get_history_raw(self, yahoo_symbol: str, period: str = "5y") -> Optional[pd.DataFrame]:
        """History for benchmarks / indexes using Yahoo's own symbol as-is (e.g. SPY, XLK, ^IRX)."""
        t = yf.Ticker(yahoo_symbol)
        try:
            df = _retry(lambda: t.history(period=period, auto_adjust=False), f"history {yahoo_symbol} {period}")
        except ProviderError as exc:
            log.warning("%s", exc)
            return None
        return df if df is not None and not df.empty else None

    @cached("yf_quote", "quote", method=True)
    def get_quote(self, symbol: str) -> Optional[Quote]:
        t = yf.Ticker(for_yfinance(symbol))

        def call():
            fi = t.fast_info
            return float(fi["lastPrice"]), float(fi["previousClose"]), fi["currency"]

        try:
            price, prev, currency = _retry(call, f"quote {symbol}")
        except ProviderError as exc:
            log.warning("%s", exc)
            return None
        if not price or price != price:  # None, 0 or NaN
            return None
        change = price - prev if prev else None
        return Quote(
            symbol=symbol, price=price, previous_close=prev, change=change,
            change_pct=(change / prev) if (change is not None and prev) else None,
            currency=currency or "USD", as_of=datetime.now(timezone.utc),
            source=self.source, license_tag=self.license_tag,
        )

    # ---------- profile ----------
    @cached("yf_info", "profile", method=True)
    def get_profile(self, symbol: str) -> Optional[dict[str, Any]]:
        """Returns Ticker.info, or None if the ticker is unknown to Yahoo."""
        t = yf.Ticker(for_yfinance(symbol))
        try:
            info = _retry(lambda: t.info, f"info {symbol}")
        except ProviderError as exc:
            log.warning("%s", exc)
            return None
        # Unknown tickers return a near-empty dict instead of raising
        if not info or not (info.get("longName") or info.get("shortName")):
            return None
        return info

    @cached("yf_industry_peers", "profile", tag_arg=None, method=True)
    def get_industry_peers(self, industry_key: str) -> Optional[list[dict[str, str]]]:
        """Top companies in the same Yahoo industry (fallback peer list).
        Only symbol and name are kept; Yahoo's 'rating' column is dropped on purpose
        (we never show buy/sell wording)."""
        try:
            df = _retry(lambda: yf.Industry(industry_key).top_companies,
                        f"industry peers {industry_key}")
        except ProviderError as exc:
            log.warning("%s", exc)
            return None
        if df is None or df.empty:
            return None
        return [{"symbol": str(sym), "name": str(row.get("name", ""))} for sym, row in df.iterrows()]

    # ---------- financial statements (backup + cross-check for SEC) ----------
    @cached("yf_statements", "statements", method=True)
    def get_statements(self, symbol: str) -> Optional[dict[str, pd.DataFrame]]:
        """{'income_q','income_a','balance_q','balance_a','cashflow_q','cashflow_a'} -> DataFrames
        (rows = line items, columns = period end dates)."""
        from concurrent.futures import ThreadPoolExecutor
        attrs = {"income_q": "quarterly_income_stmt", "income_a": "income_stmt",
                 "balance_q": "quarterly_balance_sheet", "balance_a": "balance_sheet",
                 "cashflow_q": "quarterly_cashflow", "cashflow_a": "cashflow"}

        def fetch(attr: str):
            t = yf.Ticker(for_yfinance(symbol))   # one Ticker per thread
            try:
                return _retry(lambda: getattr(t, attr), f"{attr} {symbol}")
            except ProviderError as exc:
                log.warning("%s", exc)
                return None

        with ThreadPoolExecutor(max_workers=6) as pool:   # the 6 tables in parallel instead of one by one
            results = dict(zip(attrs, pool.map(fetch, attrs.values())))
        out = {k: df for k, df in results.items() if df is not None and not df.empty}
        return out or None

    # ---------- estimates / calendar ----------
    @cached("yf_calendar", "estimates", method=True)
    def get_calendar(self, symbol: str) -> Optional[dict[str, Any]]:
        t = yf.Ticker(for_yfinance(symbol))
        try:
            cal = _retry(lambda: t.calendar, f"calendar {symbol}")
        except ProviderError as exc:
            log.warning("%s", exc)
            return None
        return cal or None

    @cached("yf_earnings_estimate", "estimates", method=True)
    def get_earnings_estimate(self, symbol: str) -> Optional[pd.DataFrame]:
        """Index: 0q, +1q, 0y, +1y. Columns: avg, low, high, numberOfAnalysts, yearAgoEps, growth."""
        t = yf.Ticker(for_yfinance(symbol))
        try:
            df = _retry(lambda: t.earnings_estimate, f"earnings_estimate {symbol}")
        except ProviderError as exc:
            log.warning("%s", exc)
            return None
        return df if df is not None and not df.empty else None

    @cached("yf_earnings_dates", "estimates", method=True)
    def get_earnings_dates(self, symbol: str, limit: int = 28) -> Optional[pd.DataFrame]:
        """Past and upcoming earnings: index = announcement datetime (tz-aware, includes time of day),
        columns 'EPS Estimate', 'Reported EPS', 'Surprise(%)' (percent units)."""
        t = yf.Ticker(for_yfinance(symbol))
        try:
            df = _retry(lambda: t.get_earnings_dates(limit=limit), f"earnings_dates {symbol}")
        except ProviderError as exc:
            log.warning("%s", exc)
            return None
        return df if df is not None and not df.empty else None

    def _frame(self, symbol: str, attr: str) -> Optional[pd.DataFrame]:
        t = yf.Ticker(for_yfinance(symbol))
        try:
            df = _retry(lambda: getattr(t, attr), f"{attr} {symbol}")
        except ProviderError as exc:
            log.warning("%s", exc)
            return None
        return df if df is not None and not df.empty else None

    # ---------- dividends / ownership / sentiment / news ----------
    @cached("yf_dividends", "estimates", method=True)
    def get_dividends(self, symbol: str) -> Optional[pd.Series]:
        """Dividend per share by ex-dividend date (split-adjusted, tz-naive). Empty Series = never paid."""
        t = yf.Ticker(for_yfinance(symbol))
        try:
            s = _retry(lambda: t.dividends, f"dividends {symbol}")
        except ProviderError as exc:
            log.warning("%s", exc)
            return None
        if s is None:
            return None
        s = s.copy()
        if len(s):
            s.index = pd.DatetimeIndex(s.index).tz_localize(None).normalize()
        return s

    @cached("yf_major_holders", "estimates", method=True)
    def get_major_holders(self, symbol: str) -> Optional[pd.DataFrame]:
        return self._frame(symbol, "major_holders")

    @cached("yf_inst_holders", "estimates", method=True)
    def get_institutional_holders(self, symbol: str) -> Optional[pd.DataFrame]:
        return self._frame(symbol, "institutional_holders")

    @cached("yf_insider_tx", "estimates", method=True)
    def get_insider_transactions(self, symbol: str) -> Optional[pd.DataFrame]:
        return self._frame(symbol, "insider_transactions")

    @cached("yf_recommendations", "estimates", method=True)
    def get_recommendations(self, symbol: str) -> Optional[pd.DataFrame]:
        """Rows period 0m/-1m/-2m/-3m with strongBuy, buy, hold, sell, strongSell counts."""
        return self._frame(symbol, "recommendations")

    @cached("yf_upgrades", "estimates", method=True)
    def get_upgrades_downgrades(self, symbol: str) -> Optional[pd.DataFrame]:
        return self._frame(symbol, "upgrades_downgrades")

    @cached("yf_news", "news", method=True)
    def get_news(self, symbol: str) -> Optional[list[dict]]:
        t = yf.Ticker(for_yfinance(symbol))
        try:
            n = _retry(lambda: t.news, f"news {symbol}")
        except ProviderError as exc:
            log.warning("%s", exc)
            return None
        return n or None

    @cached("yf_eps_trend", "estimates", method=True)
    def get_eps_trend(self, symbol: str) -> Optional[pd.DataFrame]:
        """Index 0q/+1q/0y/+1y; columns current, 7daysAgo, 30daysAgo, 60daysAgo, 90daysAgo."""
        return self._frame(symbol, "eps_trend")

    @cached("yf_eps_revisions", "estimates", method=True)
    def get_eps_revisions(self, symbol: str) -> Optional[pd.DataFrame]:
        """Index 0q/+1q/0y/+1y; columns upLast7days, upLast30days, downLast30days, downLast7Days."""
        return self._frame(symbol, "eps_revisions")

    @cached("yf_revenue_estimate", "estimates", method=True)
    def get_revenue_estimate(self, symbol: str) -> Optional[pd.DataFrame]:
        """Index 0q/+1q/0y/+1y; columns avg, low, high, numberOfAnalysts, yearAgoRevenue, growth."""
        return self._frame(symbol, "revenue_estimate")

    @cached("yf_growth_estimates", "estimates", method=True)
    def get_growth_estimates(self, symbol: str) -> Optional[pd.DataFrame]:
        """Index: 0q, +1q, 0y, +1y, LTG. Column stockTrend = expected growth (decimal)."""
        t = yf.Ticker(for_yfinance(symbol))
        try:
            df = _retry(lambda: t.growth_estimates, f"growth_estimates {symbol}")
        except ProviderError as exc:
            log.warning("%s", exc)
            return None
        return df if df is not None and not df.empty else None

    @cached("yf_price_targets", "estimates", method=True)
    def get_price_targets(self, symbol: str) -> Optional[dict]:
        """{'current','low','high','mean','median'}"""
        t = yf.Ticker(for_yfinance(symbol))
        try:
            d = _retry(lambda: t.analyst_price_targets, f"analyst_price_targets {symbol}")
        except ProviderError as exc:
            log.warning("%s", exc)
            return None
        return d if d and d.get("mean") else None

    @cached("yf_splits", "profile", method=True)
    def get_splits(self, symbol: str) -> Optional[pd.Series]:
        """Split ratios indexed by date (tz-naive), e.g. 2024-06-10 -> 10.0. Empty Series = no splits."""
        t = yf.Ticker(for_yfinance(symbol))
        try:
            s = _retry(lambda: t.splits, f"splits {symbol}")
        except ProviderError as exc:
            log.warning("%s", exc)
            return None
        if s is None:
            return None
        s = s.copy()
        if len(s):
            s.index = pd.DatetimeIndex(s.index).tz_localize(None).normalize()
        return s

    def get_next_earnings_date(self, symbol: str) -> Optional[date]:
        """Next earnings date in the future, or None. Past dates are ignored."""
        cal = self.get_calendar(symbol) or {}
        dates = cal.get("Earnings Date") or []
        if not isinstance(dates, (list, tuple)):
            dates = [dates]
        today = date.today()
        future = sorted(d for d in dates if isinstance(d, date) and d >= today)
        return future[0] if future else None
