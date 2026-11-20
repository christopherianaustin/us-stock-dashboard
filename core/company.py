"""Company header + profile service.

Combines SEC EDGAR, yfinance and Finnhub using the source priority rules and
returns models where every field carries its source and license tag.
Each source is fetched in parallel and can fail on its own without breaking the page.
"""
from __future__ import annotations

import calendar
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable, Optional

from core.logging_setup import get_logger
from core.models import (CompanyProfile, DataPoint, HeaderData, LicenseTag, Source,
                         combined_license, first_available)
from core.providers import registry
from core.providers.base import ProviderError
from core.providers.sec_edgar import COMPANY_BROWSE_URL, SecEdgarClient, is_financial_sic
from core.symbols import InvalidTickerFormat, normalize

log = get_logger("company")


class TickerNotFound(Exception):
    """Raised with a friendly, user-facing message."""


@dataclass
class ResolvedTicker:
    symbol: str                 # canonical, e.g. BRK.B
    cik: Optional[str] = None   # None if SEC doesn't list it
    sec_title: Optional[str] = None
    warnings: list[str] = field(default_factory=list)


def resolve_ticker(raw: str) -> ResolvedTicker:
    """Validate user input. Raises TickerNotFound with a friendly message."""
    try:
        symbol = normalize(raw)
    except InvalidTickerFormat as exc:
        raise TickerNotFound(str(exc)) from exc

    warnings: list[str] = []
    sec_problem: Optional[str] = None
    try:
        row = registry.sec().lookup(symbol)
        if row:
            return ResolvedTicker(symbol=symbol, cik=row["cik"], sec_title=row["title"])
    except ProviderError as exc:
        sec_problem = str(exc)
        if "SEC_USER_AGENT" in str(exc):
            warnings.append("SEC EDGAR is off: add your email to SEC_USER_AGENT in the .env file. "
                            "Showing other sources only.")
        else:
            warnings.append(f"SEC EDGAR is unavailable right now ({str(exc).rstrip('.')}). "
                            "Showing other sources only.")

    # Not in the SEC list (or SEC down): accept it if Yahoo knows it
    if registry.yfinance().get_profile(symbol):
        if not warnings:
            warnings.append("This ticker is not in the SEC company list, so official SEC data is not available.")
        return ResolvedTicker(symbol=symbol, warnings=warnings)

    if sec_problem is not None:
        # Neither source answered, so we can't tell whether the ticker exists - say so honestly.
        hint = ("Set SEC_USER_AGENT (an app name + your email) in the .env file, or in the app's Secrets when "
                "deployed on Streamlit Cloud." if "SEC_USER_AGENT" in sec_problem
                else "Please try again in a minute.")
        raise TickerNotFound(
            f"We couldn't check '{symbol}' because the data sources are not reachable right now "
            f"(SEC EDGAR: {sec_problem.rstrip('.')}; Yahoo Finance did not answer either). {hint}")

    raise TickerNotFound(
        f"We couldn't find a US-listed stock with the ticker '{symbol}'. "
        "Please check the spelling (for example AAPL for Apple, BRK.B for Berkshire Hathaway class B)."
    )


def _safe(fn: Callable[[], Any], label: str, errors: dict[str, str]) -> Any:
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001 - one source failing must never crash the page
        log.warning("%s failed: %s", label, exc)
        errors[label] = str(exc)
        return None


def fiscal_year_end_text(mmdd: Optional[str]) -> Optional[str]:
    """'0928' -> 'September 28'."""
    if not mmdd or len(mmdd) != 4 or not mmdd.isdigit():
        return None
    month, day = int(mmdd[:2]), int(mmdd[2:])
    if not 1 <= month <= 12:
        return None
    return f"{calendar.month_name[month]} {day}"


def _find_ceo(officers: list[dict]) -> Optional[str]:
    for o in officers or []:
        title = (o.get("title") or "").lower()
        if "ceo" in title or "chief executive" in title:
            return " ".join((o.get("name") or "").split()) or None
    return None


def load_header(resolved: ResolvedTicker) -> HeaderData:
    symbol, cik = resolved.symbol, resolved.cik
    sec = registry.sec()
    yf = registry.yfinance()
    fh = registry.finnhub()
    errors: dict[str, str] = {}

    tasks: dict[str, Callable[[], Any]] = {
        "yf_info": lambda: yf.get_profile(symbol),
        "yf_calendar": lambda: yf.get_next_earnings_date(symbol),
        "quote": lambda: registry.get_quote(symbol),
        "history": lambda: registry.get_history(symbol, period="1y"),
    }
    if cik:
        tasks["sec_submissions"] = lambda: sec.get_submissions(cik)
        tasks["sec_facts"] = lambda: sec.get_company_facts_by_cik(cik)
    if fh.enabled:
        tasks["fh_profile"] = lambda: fh.get_profile(symbol)
        tasks["fh_peers"] = lambda: fh.get_peers(symbol)

    with ThreadPoolExecutor(max_workers=len(tasks)) as pool:
        futures = {k: pool.submit(_safe, fn, k, errors) for k, fn in tasks.items()}
        r = {k: f.result() for k, f in futures.items()}

    subs: dict = r.get("sec_submissions") or {}
    facts: dict = r.get("sec_facts") or {}
    info: dict = r.get("yf_info") or {}
    fhp: dict = r.get("fh_profile") or {}
    quote = r.get("quote")
    history, price_src = r.get("history") or (None, None)

    warnings = list(resolved.warnings)
    if cik and (not subs or not facts):
        warnings.append("Some SEC EDGAR data could not be loaded. Showing what is available.")
    if not info:
        warnings.append("Yahoo Finance (yfinance) data could not be loaded. Some profile fields are missing.")
    if quote is None:
        warnings.append("Live price is unavailable right now.")

    profile = build_profile(symbol, cik, subs, info, fhp, r.get("fh_peers"))

    # ----- price -----
    h = HeaderData(symbol=symbol, profile=profile, warnings=warnings)
    if quote is not None:
        h.price = DataPoint.of(quote.price, quote.source, as_of=quote.as_of, license_tag=quote.license_tag)
        h.change = DataPoint.of(quote.change, quote.source, as_of=quote.as_of, license_tag=quote.license_tag)
        h.change_pct = DataPoint.of(quote.change_pct, quote.source, as_of=quote.as_of, license_tag=quote.license_tag)
    else:
        h.price = h.change = h.change_pct = DataPoint.na("Price source unavailable")

    # ----- 52-week range from daily history -----
    if history is not None and not history.empty and price_src is not None:
        last_year = history.tail(252)
        as_of = last_year.index[-1].date()
        h.week52_high = DataPoint.of(float(last_year["High"].max()), price_src.source,
                                     as_of=as_of, license_tag=price_src.license_tag)
        h.week52_low = DataPoint.of(float(last_year["Low"].min()), price_src.source,
                                    as_of=as_of, license_tag=price_src.license_tag)
    else:
        h.week52_high = h.week52_low = DataPoint.na("Price history unavailable")

    # ----- shares outstanding & market cap -----
    shares = SecEdgarClient.latest_shares_outstanding(facts) if facts else None
    if shares and shares[1] and (date.today() - shares[1]).days <= 400:
        h.shares_outstanding = DataPoint.of(shares[0], Source.SEC, as_of=shares[1])
    elif shares:
        # e.g. BRK: per-class share counts are only reported with dimensions, which the
        # SEC companyfacts API leaves out, so the newest plain value is years old.
        h.shares_outstanding = DataPoint.na(
            f"Latest SEC value is outdated ({shares[1]}); company reports shares per share class")
    else:
        h.shares_outstanding = DataPoint.na("Not reported in SEC data")
    h.market_cap = _market_cap(h, info)

    # ----- next earnings (priority: yfinance, then Finnhub) -----
    nxt = r.get("yf_calendar")
    if nxt:
        h.next_earnings_date = DataPoint.of(nxt, Source.YFINANCE)
    else:
        fh_next = _safe(lambda: fh.get_next_earnings_date(symbol), "fh_calendar", errors) if fh.enabled else None
        h.next_earnings_date = (DataPoint.of(date.fromisoformat(fh_next), Source.FINNHUB) if fh_next
                                else DataPoint.na("Next earnings date not announced yet"))

    # ----- data freshness from latest 10-Q / 10-K -----
    if subs:
        latest = SecEdgarClient.latest_periodic_report(subs)
        if latest:
            h.latest_report = latest
            period = SecEdgarClient.fiscal_period_for_accession(facts, latest.accession_number) if facts else None
            label = (f"FY{period[0]}" if period[1] == "FY" else f"{period[1]} FY{period[0]}") if period else latest.form
            text = f"Financials as of {label}"
            if latest.report_date:
                text += f" (period ended {latest.report_date.isoformat()})"
            if latest.filing_date:
                text += f", filed {latest.filing_date.isoformat()}"
            h.data_freshness = DataPoint.of(text, Source.SEC, as_of=latest.filing_date)
    if not h.data_freshness.available:
        h.data_freshness = DataPoint.na("No 10-Q/10-K found on SEC EDGAR")
    return h


def _market_cap(h: HeaderData, info: dict) -> DataPoint:
    """Market cap = price x shares outstanding (SPEC 6.4).
    Companies with several share classes (e.g. BRK, GOOGL) have different prices per
    class, so if our number is far from Yahoo's we use Yahoo's and say why."""
    yf_cap = info.get("marketCap")
    if h.price.available and h.shares_outstanding.available:
        calc = h.price.value * h.shares_outstanding.value
        lic = combined_license(h.price.license_tag, h.shares_outstanding.license_tag)
        if yf_cap and abs(calc / yf_cap - 1) > 0.25:
            log.info("Market cap mismatch for %s: calc %.3g vs yfinance %.3g", h.symbol, calc, yf_cap)
            return DataPoint.of(float(yf_cap), Source.YFINANCE,
                                note="Company has more than one share class; using Yahoo's total market cap.")
        return DataPoint.of(calc, Source.CALCULATED, license_tag=lic, derived=True,
                            note="Price x shares outstanding (SEC)")
    if yf_cap:
        return DataPoint.of(float(yf_cap), Source.YFINANCE)
    return DataPoint.na("Needs price and shares outstanding")


def build_profile(symbol: str, cik: Optional[str], subs: dict, info: dict, fhp: dict,
                  fh_peers: Optional[list[str]]) -> CompanyProfile:
    S, Y, F = Source.SEC, Source.YFINANCE, Source.FINNHUB
    p = CompanyProfile(symbol=symbol, cik=cik)
    if cik:
        p.sec_filings_url = COMPANY_BROWSE_URL.format(cik=cik)

    # Exchange as listed by SEC for this exact ticker
    sec_exchange = None
    tickers, exchanges = subs.get("tickers") or [], subs.get("exchanges") or []
    for tk, ex in zip(tickers, exchanges):
        if tk.upper().replace("-", ".") == symbol:
            sec_exchange = ex
    biz = (subs.get("addresses") or {}).get("business") or {}
    city = (biz.get("city") or "").title() or None
    sec_hq = ", ".join(x for x in [city, biz.get("stateOrCountryDescription") or biz.get("stateOrCountry")] if x)
    yf_hq = ", ".join(x for x in [info.get("city"), info.get("state"), info.get("country")] if x)

    p.name = first_available(DataPoint.of(subs.get("name"), S), DataPoint.of(info.get("longName"), Y),
                             DataPoint.of(fhp.get("name"), F))
    # SEC names are often ALL CAPS ("JPMORGAN CHASE & CO"); keep a nicer display version
    p.display_name = first_available(DataPoint.of(info.get("longName"), Y), DataPoint.of(fhp.get("name"), F))
    p.exchange = first_available(DataPoint.of(sec_exchange, S), DataPoint.of(info.get("fullExchangeName"), Y),
                                 DataPoint.of(fhp.get("exchange"), F))
    p.sector = first_available(DataPoint.of(info.get("sector"), Y),
                               reason="Sector not available (SEC only provides an SIC industry code)")
    p.industry = first_available(DataPoint.of(info.get("industry"), Y), DataPoint.of(fhp.get("finnhubIndustry"), F))
    p.sic_code = DataPoint.of(subs.get("sic"), S, na_reason="Not available (company not in SEC data)")
    p.sic_description = DataPoint.of(subs.get("sicDescription"), S, na_reason="Not available (company not in SEC data)")
    p.description = DataPoint.of(info.get("longBusinessSummary"), Y, na_reason="Business description not available")
    p.employees = DataPoint.of(info.get("fullTimeEmployees"), Y, na_reason="Not reported")
    p.headquarters = first_available(DataPoint.of(sec_hq, S), DataPoint.of(yf_hq, Y))
    p.website = first_available(DataPoint.of(subs.get("website"), S), DataPoint.of(fhp.get("weburl"), F),
                                DataPoint.of(info.get("website"), Y))
    p.ceo = DataPoint.of(_find_ceo(info.get("companyOfficers") or []), Y, na_reason="CEO not listed by the data source")
    fye = fiscal_year_end_text(subs.get("fiscalYearEnd"))
    last_10k = SecEdgarClient.recent_filings(subs, forms={"10-K", "20-F", "40-F"}, limit=1) if subs else []
    if fye and last_10k and last_10k[0].report_date:
        # Many companies (e.g. Apple) use 52/53-week years, so the exact day moves a little
        fye += f" (latest year ended {last_10k[0].report_date.isoformat()})"
    p.fiscal_year_end = DataPoint.of(fye, S, na_reason="Not available (company not in SEC data)")
    p.ipo_date = DataPoint.of(fhp.get("ipo"), F,
                              na_reason="IPO date needs Finnhub (add FINNHUB_API_KEY)" if not fhp else "Not reported")
    p.logo_url = DataPoint.of(fhp.get("logo"), F)
    p.state_of_incorporation = DataPoint.of(subs.get("stateOfIncorporationDescription") or subs.get("stateOfIncorporation"), S)

    # Peers: Finnhub, then same Yahoo industry (SEC same-SIC needs a bulk index; planned later)
    peers: list[str] = []
    peer_src = None
    if fh_peers:
        peers, peer_src = list(dict.fromkeys(fh_peers))[:8], F
    elif info.get("industryKey"):
        rows = registry.yfinance().get_industry_peers(info["industryKey"]) or []
        me = symbol.replace(".", "-")
        peers = [r["symbol"].replace("-", ".") for r in rows if r["symbol"].upper() != me][:8]
        peer_src = Y
    p.peers = DataPoint.of(peers, peer_src, na_reason="No peer list available") if peer_src else DataPoint.na("No peer list available")

    sector_l = (info.get("sector") or "").lower()
    industry_l = (info.get("industry") or "").lower()
    p.is_financial_company = is_financial_sic(subs.get("sic")) or (
        sector_l == "financial services" and any(w in industry_l for w in ("bank", "insurance")))
    return p
