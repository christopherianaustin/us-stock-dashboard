"""SEC EDGAR client (license tag: COMMERCIAL_OK).

Rules from the SEC: send a User-Agent with a real contact on every request,
stay under 10 requests per second, cache heavily.
"""
from __future__ import annotations

import threading
import time
from datetime import date, datetime
from typing import Any, Optional

import requests

from config.settings import settings
from core.cache import cached
from core.logging_setup import get_logger, log_call
from core.models import Filing, LicenseTag, Source
from core.providers.base import FundamentalsProvider, ProviderError
from core.symbols import for_sec

log = get_logger("sec")

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
ARCHIVE_URL = "https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_nodash}/{doc}"
INDEX_URL = "https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_nodash}/"
COMPANY_BROWSE_URL = "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type=&dateb=&owner=include&count=40"

# SIC codes for banks, savings institutions, credit, insurance (special handling later)
FINANCIAL_SIC_RANGES = [(6000, 6299), (6300, 6499)]


class _RateLimiter:
    """Allow at most `per_second` calls per second across all threads."""

    def __init__(self, per_second: float):
        self.min_interval = 1.0 / per_second
        self._lock = threading.Lock()
        self._last = 0.0

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            sleep_for = self._last + self.min_interval - now
            if sleep_for > 0:
                time.sleep(sleep_for)
            self._last = time.monotonic()


_limiter = _RateLimiter(per_second=8)  # safely under the SEC limit of 10


def pad_cik(cik: int | str) -> str:
    return str(int(cik)).zfill(10)


def filing_urls(cik: str | int, accession: str, primary_document: Optional[str]) -> tuple[Optional[str], str]:
    cik_int = int(cik)
    acc_nodash = accession.replace("-", "")
    doc_url = ARCHIVE_URL.format(cik_int=cik_int, acc_nodash=acc_nodash, doc=primary_document) if primary_document else None
    return doc_url, INDEX_URL.format(cik_int=cik_int, acc_nodash=acc_nodash)


def _parse_date(s: Any) -> Optional[date]:
    if not s:
        return None
    try:
        return datetime.strptime(str(s)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def is_financial_sic(sic: Any) -> bool:
    try:
        code = int(sic)
    except (TypeError, ValueError):
        return False
    return any(lo <= code <= hi for lo, hi in FINANCIAL_SIC_RANGES)


class SecEdgarClient(FundamentalsProvider):
    source = Source.SEC
    license_tag = LicenseTag.COMMERCIAL_OK

    def __init__(self, user_agent: Optional[str] = None):
        self.user_agent = user_agent or settings.sec_user_agent
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": self.user_agent, "Accept-Encoding": "gzip, deflate"})

    def _get_json(self, url: str, what: str, retries: int = 3) -> dict | list:
        if not self.user_agent:
            raise ProviderError("SEC_USER_AGENT is not set in .env (SEC requires a contact email).")
        last: Exception | None = None
        for attempt in range(retries):
            _limiter.wait()
            try:
                with log_call("SEC EDGAR", what):
                    r = self.session.get(url, timeout=20)
                    if r.status_code == 404:
                        raise ProviderError(f"SEC: not found ({what})")
                    if r.status_code in (403, 429):
                        raise requests.HTTPError(f"SEC returned {r.status_code} (check SEC_USER_AGENT / rate limit)")
                    r.raise_for_status()
                    return r.json()
            except ProviderError:
                raise
            except Exception as exc:  # noqa: BLE001
                last = exc
                if attempt < retries - 1:
                    time.sleep(1.0 * (2 ** attempt))
        raise ProviderError(f"SEC request failed ({what}): {last}")

    # ---------- ticker -> CIK ----------
    @cached("sec_tickers", "sec_tickers", tag_arg=None, method=True)
    def get_ticker_map(self) -> dict[str, dict[str, Any]]:
        """{'AAPL': {'cik': '0000320193', 'title': 'Apple Inc.'}, 'BRK-B': {...}, ...}"""
        data = self._get_json(TICKERS_URL, "company_tickers.json")
        out: dict[str, dict[str, Any]] = {}
        for row in data.values():
            tk = str(row["ticker"]).upper()
            out[tk] = {"cik": pad_cik(row["cik_str"]), "title": row["title"]}
        return out

    def lookup(self, symbol: str) -> Optional[dict[str, Any]]:
        """Return {'cik', 'title', 'ticker'} or None if the SEC doesn't know this ticker."""
        tk = for_sec(symbol)
        row = self.get_ticker_map().get(tk)
        return {**row, "ticker": tk} if row else None

    # ---------- submissions & facts ----------
    @cached("sec_submissions", "sec_submissions", method=True)
    def get_submissions(self, cik: str) -> dict[str, Any]:
        return self._get_json(SUBMISSIONS_URL.format(cik=pad_cik(cik)), f"submissions {cik}")

    @cached("sec_companyfacts", "sec_companyfacts", method=True)
    def get_company_facts_by_cik(self, cik: str) -> dict[str, Any]:
        return self._get_json(COMPANYFACTS_URL.format(cik=pad_cik(cik)), f"companyfacts {cik}")

    def get_company_facts(self, symbol: str) -> dict[str, Any]:
        row = self.lookup(symbol)
        if not row:
            raise ProviderError(f"SEC does not list ticker {symbol}")
        return self.get_company_facts_by_cik(row["cik"])

    # ---------- helpers on submissions ----------
    @staticmethod
    def recent_filings(submissions: dict[str, Any], forms: Optional[set[str]] = None,
                       limit: Optional[int] = 50) -> list[Filing]:
        recent = submissions.get("filings", {}).get("recent", {})
        cik = submissions.get("cik")
        n = len(recent.get("accessionNumber", []))
        out: list[Filing] = []
        for i in range(n):
            form = recent["form"][i]
            if forms and form not in forms:
                continue
            acc = recent["accessionNumber"][i]
            doc = (recent.get("primaryDocument") or [None] * n)[i]
            doc_url, idx_url = filing_urls(cik, acc, doc) if cik else (None, None)
            out.append(Filing(
                form=form,
                filing_date=_parse_date(recent.get("filingDate", [None] * n)[i]),
                report_date=_parse_date((recent.get("reportDate") or [None] * n)[i]),
                accession_number=acc,
                primary_document=doc,
                description=(recent.get("primaryDocDescription") or [None] * n)[i],
                items=(recent.get("items") or [None] * n)[i] or None,
                url=doc_url,
                index_url=idx_url,
            ))
            if limit is not None and len(out) >= limit:
                break
        return out

    @staticmethod
    def latest_periodic_report(submissions: dict[str, Any]) -> Optional[Filing]:
        """Most recent 10-Q or 10-K (includes amended and foreign 20-F/40-F)."""
        filings = SecEdgarClient.recent_filings(
            submissions, forms={"10-Q", "10-K", "10-Q/A", "10-K/A", "20-F", "40-F"}, limit=1)
        return filings[0] if filings else None

    @staticmethod
    def fiscal_period_for_accession(facts: dict[str, Any], accession: str) -> Optional[tuple[int, str]]:
        """Find (fiscal_year, fiscal_period e.g. 'Q3'/'FY') reported in a given filing."""
        for taxonomy in ("dei", "us-gaap"):
            for concept in (facts.get("facts", {}).get(taxonomy) or {}).values():
                for unit_rows in concept.get("units", {}).values():
                    for row in unit_rows:
                        if row.get("accn") == accession and row.get("fy") and row.get("fp"):
                            return int(row["fy"]), str(row["fp"])
        return None

    @staticmethod
    def latest_shares_outstanding(facts: dict[str, Any]) -> Optional[tuple[float, date]]:
        """dei:EntityCommonStockSharesOutstanding from the newest filing.
        Multi-class companies report one value per class on the same date; we sum them."""
        concept = facts.get("facts", {}).get("dei", {}).get("EntityCommonStockSharesOutstanding")
        if not concept:
            concept = facts.get("facts", {}).get("us-gaap", {}).get("CommonStockSharesOutstanding")
        if not concept:
            return None
        rows = concept.get("units", {}).get("shares", [])
        if not rows:
            return None
        latest_end = max(r["end"] for r in rows)
        latest_filed = max(r["filed"] for r in rows if r["end"] == latest_end)
        same = {r["val"] for r in rows if r["end"] == latest_end and r["filed"] == latest_filed}
        return float(sum(same)), _parse_date(latest_end)
