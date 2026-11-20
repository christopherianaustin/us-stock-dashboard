"""Pydantic data models. Every value carries its source and license tag (SPEC Section 9)."""
from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class Source(str, Enum):
    SEC = "SEC EDGAR"
    YFINANCE = "yfinance"
    FINNHUB = "Finnhub"
    NANOVEST = "Nanovest"
    CALCULATED = "Calculated"


class LicenseTag(str, Enum):
    COMMERCIAL_OK = "COMMERCIAL_OK"      # SEC EDGAR, Nanovest price feed
    CALCULATED_SAFE = "CALCULATED_SAFE"  # calculated only from COMMERCIAL_OK inputs
    DEMO_ONLY = "DEMO_ONLY"              # yfinance / Finnhub free, or calculated from them


# Default license per source
SOURCE_LICENSE = {
    Source.SEC: LicenseTag.COMMERCIAL_OK,
    Source.NANOVEST: LicenseTag.COMMERCIAL_OK,
    Source.YFINANCE: LicenseTag.DEMO_ONLY,
    Source.FINNHUB: LicenseTag.DEMO_ONLY,
}


def combined_license(*tags: LicenseTag) -> LicenseTag:
    """License of a value calculated from several inputs: DEMO_ONLY if any input is."""
    if any(t == LicenseTag.DEMO_ONLY for t in tags):
        return LicenseTag.DEMO_ONLY
    return LicenseTag.CALCULATED_SAFE


class DataPoint(BaseModel):
    """One value plus where it came from. `value is None` means not available,
    and `na_reason` explains why in plain language."""

    value: Any = None
    source: Optional[Source] = None
    license_tag: Optional[LicenseTag] = None
    derived: bool = False
    as_of: Optional[date | datetime] = None
    na_reason: Optional[str] = None
    note: Optional[str] = None

    @property
    def available(self) -> bool:
        return self.value is not None and self.value != "" and self.value != []

    @classmethod
    def of(cls, value: Any, source: Source, *, as_of=None, derived: bool = False,
           license_tag: LicenseTag | None = None, note: str | None = None,
           na_reason: str = "Not reported by this data source") -> "DataPoint":
        """Build a DataPoint; empty values automatically become N/A."""
        if value is None or (isinstance(value, str) and not value.strip()) or value == []:
            return cls.na(na_reason)
        return cls(value=value, source=source,
                   license_tag=license_tag or SOURCE_LICENSE.get(source, LicenseTag.DEMO_ONLY),
                   derived=derived, as_of=as_of, note=note)

    @classmethod
    def na(cls, reason: str = "Data source unavailable") -> "DataPoint":
        return cls(value=None, na_reason=reason)


def first_available(*points: DataPoint, reason: str = "Not available from any source") -> DataPoint:
    """Source priority helper: return the first DataPoint that has a value."""
    for p in points:
        if p is not None and p.available:
            return p
    reasons = [p.na_reason for p in points if p is not None and p.na_reason]
    return DataPoint.na(reasons[0] if len(set(reasons)) == 1 else reason)


class Quote(BaseModel):
    symbol: str
    price: Optional[float] = None
    previous_close: Optional[float] = None
    change: Optional[float] = None
    change_pct: Optional[float] = None
    currency: Optional[str] = "USD"
    as_of: Optional[datetime] = None
    source: Source
    license_tag: LicenseTag


class Filing(BaseModel):
    form: str
    filing_date: Optional[date] = None
    report_date: Optional[date] = None
    accession_number: str
    primary_document: Optional[str] = None
    description: Optional[str] = None
    items: Optional[str] = None          # 8-K item codes, e.g. "2.02,9.01" (2.02 = results of operations)
    url: Optional[str] = None
    index_url: Optional[str] = None


class CompanyProfile(BaseModel):
    """Profile fields shown in the header and the Company Profile tab."""

    symbol: str
    cik: Optional[str] = None
    name: DataPoint = Field(default_factory=DataPoint.na)          # official SEC name
    display_name: DataPoint = Field(default_factory=DataPoint.na)  # nicer casing (demo sources)
    exchange: DataPoint = Field(default_factory=DataPoint.na)
    sector: DataPoint = Field(default_factory=DataPoint.na)
    industry: DataPoint = Field(default_factory=DataPoint.na)
    sic_code: DataPoint = Field(default_factory=DataPoint.na)
    sic_description: DataPoint = Field(default_factory=DataPoint.na)
    description: DataPoint = Field(default_factory=DataPoint.na)
    employees: DataPoint = Field(default_factory=DataPoint.na)
    headquarters: DataPoint = Field(default_factory=DataPoint.na)
    website: DataPoint = Field(default_factory=DataPoint.na)
    ceo: DataPoint = Field(default_factory=DataPoint.na)
    fiscal_year_end: DataPoint = Field(default_factory=DataPoint.na)
    ipo_date: DataPoint = Field(default_factory=DataPoint.na)
    logo_url: DataPoint = Field(default_factory=DataPoint.na)
    state_of_incorporation: DataPoint = Field(default_factory=DataPoint.na)
    peers: DataPoint = Field(default_factory=DataPoint.na)
    sec_filings_url: Optional[str] = None
    is_financial_company: bool = False  # banks/insurers: special handling in later phases


class HeaderData(BaseModel):
    """Everything the always-visible header needs."""

    symbol: str
    profile: CompanyProfile
    price: DataPoint = Field(default_factory=DataPoint.na)
    change: DataPoint = Field(default_factory=DataPoint.na)
    change_pct: DataPoint = Field(default_factory=DataPoint.na)
    market_cap: DataPoint = Field(default_factory=DataPoint.na)
    shares_outstanding: DataPoint = Field(default_factory=DataPoint.na)
    week52_high: DataPoint = Field(default_factory=DataPoint.na)
    week52_low: DataPoint = Field(default_factory=DataPoint.na)
    next_earnings_date: DataPoint = Field(default_factory=DataPoint.na)
    data_freshness: DataPoint = Field(default_factory=DataPoint.na)
    latest_report: Optional[Filing] = None
    warnings: list[str] = Field(default_factory=list)
