"""Phase 1 unit tests (no internet needed)."""
from datetime import date

import pytest

from core.company import _find_ceo, fiscal_year_end_text
from core.models import DataPoint, LicenseTag, Source, combined_license, first_available
from core.providers.sec_edgar import SecEdgarClient, filing_urls, is_financial_sic, pad_cik
from core.symbols import InvalidTickerFormat, for_finnhub, for_sec, for_yfinance, normalize


# ---------- tickers ----------
@pytest.mark.parametrize("raw,expected", [
    ("aapl", "AAPL"), (" AAPL ", "AAPL"), ("$tsla", "TSLA"),
    ("BRK-B", "BRK.B"), ("brk.b", "BRK.B"), ("BRK/B", "BRK.B"), ("brk b", "BRKB"),
])
def test_normalize(raw, expected):
    assert normalize(raw) == expected


@pytest.mark.parametrize("raw", ["", "   ", "AAPL!", "TOOLONGTICKER", "A..B", "12345678"])
def test_normalize_rejects_bad_input(raw):
    with pytest.raises(InvalidTickerFormat):
        normalize(raw)


def test_per_source_spelling():
    assert for_sec("BRK.B") == "BRK-B"
    assert for_yfinance("brk.b") == "BRK-B"
    assert for_finnhub("BRK-B") == "BRK.B"


# ---------- models / license ----------
def test_datapoint_empty_values_become_na():
    assert not DataPoint.of(None, Source.SEC).available
    assert not DataPoint.of("  ", Source.SEC).available
    assert not DataPoint.of([], Source.SEC).available
    assert DataPoint.of(0, Source.SEC).available  # zero is a real value


def test_default_license_by_source():
    assert DataPoint.of(1, Source.SEC).license_tag == LicenseTag.COMMERCIAL_OK
    assert DataPoint.of(1, Source.YFINANCE).license_tag == LicenseTag.DEMO_ONLY
    assert DataPoint.of(1, Source.FINNHUB).license_tag == LicenseTag.DEMO_ONLY


def test_combined_license():
    assert combined_license(LicenseTag.COMMERCIAL_OK, LicenseTag.COMMERCIAL_OK) == LicenseTag.CALCULATED_SAFE
    assert combined_license(LicenseTag.COMMERCIAL_OK, LicenseTag.DEMO_ONLY) == LicenseTag.DEMO_ONLY


def test_first_available_priority():
    a = DataPoint.na("missing")
    b = DataPoint.of("from yf", Source.YFINANCE)
    c = DataPoint.of("from fh", Source.FINNHUB)
    assert first_available(a, b, c).value == "from yf"
    assert not first_available(a, DataPoint.na("missing")).available


# ---------- SEC helpers ----------
def test_pad_cik_and_urls():
    assert pad_cik(320193) == "0000320193"
    doc, idx = filing_urls("0000320193", "0000320193-25-000079", "aapl-20250927.htm")
    assert doc == "https://www.sec.gov/Archives/edgar/data/320193/000032019325000079/aapl-20250927.htm"
    assert idx.endswith("/000032019325000079/")


def test_is_financial_sic():
    assert is_financial_sic("6021")  # national commercial banks (JPM)
    assert is_financial_sic(6331)    # insurance
    assert not is_financial_sic("3571")  # computers (AAPL)
    assert not is_financial_sic(None)


FAKE_SUBMISSIONS = {
    "cik": "0000320193",
    "filings": {"recent": {
        "accessionNumber": ["A-1", "A-2", "A-3"],
        "form": ["8-K", "10-Q", "10-K"],
        "filingDate": ["2026-10-30", "2026-08-01", "2025-10-31"],
        "reportDate": ["2026-10-30", "2026-06-27", "2025-09-27"],
        "primaryDocument": ["x.htm", "q.htm", "k.htm"],
        "primaryDocDescription": ["8-K", "10-Q", "10-K"],
    }},
}


def test_latest_periodic_report_skips_8k():
    f = SecEdgarClient.latest_periodic_report(FAKE_SUBMISSIONS)
    assert f.form == "10-Q"
    assert f.report_date == date(2026, 6, 27)
    assert f.filing_date == date(2026, 8, 1)


def test_fiscal_period_for_accession():
    facts = {"facts": {"dei": {"X": {"units": {"shares": [
        {"accn": "A-2", "fy": 2026, "fp": "Q3", "val": 1}]}}}}}
    assert SecEdgarClient.fiscal_period_for_accession(facts, "A-2") == (2026, "Q3")
    assert SecEdgarClient.fiscal_period_for_accession(facts, "nope") is None


def test_latest_shares_outstanding_sums_classes():
    facts = {"facts": {"dei": {"EntityCommonStockSharesOutstanding": {"units": {"shares": [
        {"end": "2025-01-01", "filed": "2025-02-01", "val": 100},
        {"end": "2026-07-20", "filed": "2026-08-01", "val": 1000},   # class A
        {"end": "2026-07-20", "filed": "2026-08-01", "val": 500},    # class B
    ]}}}}}
    shares, as_of = SecEdgarClient.latest_shares_outstanding(facts)
    assert shares == 1500 and as_of == date(2026, 7, 20)


# ---------- profile helpers ----------
def test_fiscal_year_end_text():
    assert fiscal_year_end_text("0928") == "September 28"
    assert fiscal_year_end_text("1231") == "December 31"
    assert fiscal_year_end_text(None) is None
    assert fiscal_year_end_text("1399") is None


def test_find_ceo():
    officers = [{"name": "A", "title": "Senior VP & CFO"}, {"name": "Mr.  Tim  Cook", "title": "CEO & Director"}]
    assert _find_ceo(officers) == "Mr. Tim Cook"
    assert _find_ceo([]) is None
