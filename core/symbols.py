"""Ticker symbol cleanup and per-source spelling.

Share classes are written differently by each source:
    canonical (what we show) : BRK.B
    SEC EDGAR ticker list    : BRK-B
    yfinance                 : BRK-B
    Finnhub                  : BRK.B
"""
from __future__ import annotations

import re

_VALID = re.compile(r"^[A-Z0-9]{1,6}(\.[A-Z0-9]{1,3})?$")


class InvalidTickerFormat(ValueError):
    pass


def normalize(raw: str) -> str:
    """Clean user input into our canonical form (uppercase, class separator '.')."""
    if raw is None:
        raise InvalidTickerFormat("Please type a ticker symbol, for example AAPL.")
    s = raw.strip().upper().lstrip("$")
    s = re.sub(r"\s+", "", s)
    s = s.replace("-", ".").replace("/", ".")
    if not s:
        raise InvalidTickerFormat("Please type a ticker symbol, for example AAPL.")
    if not _VALID.match(s):
        raise InvalidTickerFormat(
            f"'{raw.strip()}' does not look like a US ticker symbol. "
            "Use letters only, for example AAPL, MSFT or BRK.B."
        )
    return s


def for_sec(symbol: str) -> str:
    return normalize(symbol).replace(".", "-")


def for_yfinance(symbol: str) -> str:
    return normalize(symbol).replace(".", "-")


def for_finnhub(symbol: str) -> str:
    return normalize(symbol)
