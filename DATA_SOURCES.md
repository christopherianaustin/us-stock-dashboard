# Data sources

Every field the dashboard shows, where it comes from, whether it may be used commercially, and what could replace it
in production. **Generated from `core/coverage.py`** (run `python scripts/make_data_sources.py`), the same catalog that
powers the in-app *Data Coverage* tab and the `GET /coverage/{ticker}` API endpoint.

## License tags

| Tag | Meaning |
|---|---|
| 🟢 COMMERCIAL_OK | From SEC EDGAR or the Nanovest price feed. OK for commercial use. |
| 🔵 CALCULATED_SAFE | Calculated by us only from COMMERCIAL_OK inputs. OK for commercial use. |
| 🟠 DEMO_ONLY | From yfinance or Finnhub's free tier, or calculated using them. **Demo only**: replace before launch. |

With `PRODUCTION_SAFE_MODE=true` every DEMO_ONLY item is hidden and shows "Requires a licensed data provider".

## Biggest wins when going to production

1. **Connect the Nanovest price feed** (`core/providers/nanovest_price.py`, then `PRICE_PROVIDER=nanovest`).
   Every price-based ratio, technical indicator, risk metric and the valuation history turn into CALCULATED_SAFE
   automatically, because they are calculated from SEC data plus the price.
2. **Parse SEC 13F and Form 4 filings directly** (free, licensed-safe) for institutional holders and insider trades.
3. **License one estimates vendor** (EPS / revenue estimates, revisions, earnings calendar, analyst ratings and price
   targets): this replaces the whole Earnings tab's demo data and parts of Valuation and Ownership.
4. **License a news feed and a corporate-actions feed** (dividends, splits, ex-dates).
5. **Risk-free rate**: switch `^IRX` to the US Treasury's daily rates (public domain).

## All fields


### Profile

| Field | Source | License | Where it comes from | Production replacement |
|---|---|---|---|---|
| Company name | SEC EDGAR | 🟢 COMMERCIAL_OK | `submissions JSON: name` | already licensed-safe |
| Exchange | SEC EDGAR | 🟢 COMMERCIAL_OK | `submissions JSON: exchanges` | already licensed-safe |
| SIC industry code | SEC EDGAR | 🟢 COMMERCIAL_OK | `submissions JSON: sic, sicDescription` | already licensed-safe |
| Headquarters | SEC EDGAR | 🟢 COMMERCIAL_OK | `submissions JSON: addresses.business` | already licensed-safe |
| Fiscal year end | SEC EDGAR | 🟢 COMMERCIAL_OK | `submissions JSON: fiscalYearEnd + latest 10-K` | already licensed-safe |
| State of incorporation | SEC EDGAR | 🟢 COMMERCIAL_OK | `submissions JSON` | already licensed-safe |
| Sector | yfinance | 🟠 DEMO_ONLY | `Ticker.info['sector']` | GICS sector (S&P/MSCI license) or SIC mapping from SEC |
| Industry | yfinance, Finnhub | 🟠 DEMO_ONLY | `Ticker.info['industry']; /stock/profile2` | GICS industry (license) or SEC SIC description |
| Business description | yfinance | 🟠 DEMO_ONLY | `Ticker.info['longBusinessSummary']` | Company 10-K text (SEC, free) or a licensed reference-data vendor |
| Employees | yfinance | 🟠 DEMO_ONLY | `Ticker.info['fullTimeEmployees']` | 10-K human capital section (SEC) or reference-data vendor |
| CEO | yfinance | 🟠 DEMO_ONLY | `Ticker.info['companyOfficers']` | SEC DEF 14A / 10-K or reference-data vendor |
| Website | SEC EDGAR, Finnhub, yfinance | 🟠 DEMO_ONLY | `submissions website; /stock/profile2 weburl` | Company 10-K text (SEC, free) or a licensed reference-data vendor |
| IPO date | Finnhub | 🟠 DEMO_ONLY | `/stock/profile2 ipo` | Reference-data vendor |
| Logo | Finnhub | 🟠 DEMO_ONLY | `/stock/profile2 logo` | Licensed logo API or Nanovest's own assets |
| Peer list | Finnhub, yfinance | 🟠 DEMO_ONLY | `/stock/peers; yf.Industry(...).top_companies` | Own peer engine on SEC SIC codes (licensed-safe) or FactSet peers |

### Header

| Field | Source | License | Where it comes from | Production replacement |
|---|---|---|---|---|
| Price and change today | yfinance | 🟠 DEMO_ONLY | `Ticker.fast_info lastPrice, previousClose` | Nanovest price feed (PRICE_PROVIDER=nanovest) or licensed exchange data (e.g. Nasdaq / NYSE via a data vendor) |
| Shares outstanding | SEC EDGAR | 🟢 COMMERCIAL_OK | `dei:EntityCommonStockSharesOutstanding` | already licensed-safe |
| Market cap | Calculated (price x SEC shares) | 🟠 DEMO_ONLY | `price x shares; yfinance marketCap for multi-class shares` | Becomes Calculated with the Nanovest price feed |
| 52-week high / low | yfinance (price history) | 🟠 DEMO_ONLY | `Ticker.history(period='1y')` | Nanovest price feed (PRICE_PROVIDER=nanovest) or licensed exchange data (e.g. Nasdaq / NYSE via a data vendor) |
| Next earnings date | yfinance, Finnhub | 🟠 DEMO_ONLY | `Ticker.calendar; /calendar/earnings` | Licensed earnings calendar: Wall Street Horizon, Nasdaq, Benzinga |
| Data freshness (latest 10-Q/10-K) | SEC EDGAR | 🟢 COMMERCIAL_OK | `submissions filings + companyfacts fy/fp` | already licensed-safe |

### Financials

| Field | Source | License | Where it comes from | Production replacement |
|---|---|---|---|---|
| Revenue | SEC EDGAR | 🟢 COMMERCIAL_OK | `XBRL tags in config/xbrl_tags.yaml (revenue)` | already licensed-safe |
| Cost of revenue / gross profit | SEC EDGAR | 🟢 COMMERCIAL_OK | `CostOfRevenue..., GrossProfit (else revenue - cost)` | already licensed-safe |
| Operating income | SEC EDGAR | 🟢 COMMERCIAL_OK | `OperatingIncomeLoss` | already licensed-safe |
| Net income | SEC EDGAR | 🟢 COMMERCIAL_OK | `NetIncomeLoss, ProfitLoss` | already licensed-safe |
| EPS (diluted, GAAP) | SEC EDGAR | 🟢 COMMERCIAL_OK | `EarningsPerShareDiluted (Q4 = NI / shares)` | already licensed-safe |
| Total assets / liabilities / equity | SEC EDGAR | 🟢 COMMERCIAL_OK | `Assets, Liabilities, StockholdersEquity` | already licensed-safe |
| Cash and short-term investments | SEC EDGAR | 🟢 COMMERCIAL_OK | `CashAndCashEquivalents..., ShortTermInvestments` | already licensed-safe |
| Total debt | Calculated from SEC | 🔵 CALCULATED_SAFE | `DebtCurrent... + LongTermDebt...` | already licensed-safe |
| Operating cash flow (YTD fixed) | SEC EDGAR | 🟢 COMMERCIAL_OK | `NetCashProvidedByUsedInOperatingActivities` | already licensed-safe |
| Capex | SEC EDGAR | 🟢 COMMERCIAL_OK | `PaymentsToAcquirePropertyPlantAndEquipment` | already licensed-safe |
| Free cash flow | Calculated from SEC | 🔵 CALCULATED_SAFE | `OCF - capex` | already licensed-safe |
| EBITDA | Calculated from SEC | 🔵 CALCULATED_SAFE | `operating income + D&A` | already licensed-safe |
| Dividends paid / buybacks | SEC EDGAR | 🟢 COMMERCIAL_OK | `PaymentsOfDividends, PaymentsForRepurchaseOfCommonStock` | already licensed-safe |
| Dividends declared per share | SEC EDGAR | 🟢 COMMERCIAL_OK | `CommonStockDividendsPerShareDeclared` | already licensed-safe |
| SEC vs yfinance cross-check | SEC EDGAR + yfinance | 🟠 DEMO_ONLY | `last 4 quarters, >2% logged` | Cross-check against a licensed fundamentals vendor |

### Ratios

| Field | Source | License | Where it comes from | Production replacement |
|---|---|---|---|---|
| ROE / ROA / ROIC | Calculated from SEC | 🔵 CALCULATED_SAFE | `core/ratios.py` | already licensed-safe |
| Margins (gross, operating, net) | Calculated from SEC | 🔵 CALCULATED_SAFE | `core/ratios.py` | already licensed-safe |
| Debt to equity, current ratio, interest coverage | Calculated from SEC | 🔵 CALCULATED_SAFE | `core/ratios.py` | already licensed-safe |
| Revenue / EPS growth and CAGR | Calculated from SEC | 🔵 CALCULATED_SAFE | `core/ratios.py` | already licensed-safe |
| Piotroski F-score | Calculated from SEC | 🔵 CALCULATED_SAFE | `core/quality_scores.py` | already licensed-safe |
| P/E, P/S, P/B, EV/EBITDA, FCF yield | Calculated (SEC + price) | 🟠 DEMO_ONLY | `core/ratios.py` | Becomes Calculated with the Nanovest price feed |
| Altman Z-score | Calculated (SEC + market cap) | 🟠 DEMO_ONLY | `core/quality_scores.py` | Becomes Calculated with the Nanovest price feed |

### Valuation

| Field | Source | License | Where it comes from | Production replacement |
|---|---|---|---|---|
| 5-year valuation history (no look-ahead) | Calculated (SEC + daily prices) | 🟠 DEMO_ONLY | `core/valuation.py` | Becomes Calculated with Nanovest price history |
| Stock split adjustments | yfinance | 🟠 DEMO_ONLY | `Ticker.splits` | Licensed corporate-actions feed |
| Forward P/E, PEG | yfinance estimates | 🟠 DEMO_ONLY | `Ticker.earnings_estimate, growth_estimates` | Licensed estimates: LSEG I/B/E/S, FactSet Estimates, S&P Capital IQ, Zacks |
| Peer ratios | yfinance | 🟠 DEMO_ONLY | `Ticker.info (trailingPE, priceToSales...) for each peer` | Compute peers from SEC (licensed-safe) + licensed prices |
| Graham number | Calculated from SEC | 🔵 CALCULATED_SAFE | `sqrt(22.5 x EPS x BVPS)` | already licensed-safe |
| DCF inputs (default growth) | yfinance estimates or SEC FCF CAGR | 🟠 DEMO_ONLY | `core/valuation.py` | Licensed estimates or SEC-only defaults |
| Analyst price targets | yfinance | 🟠 DEMO_ONLY | `Ticker.analyst_price_targets` | Licensed estimates: LSEG I/B/E/S, FactSet Estimates, S&P Capital IQ, Zacks |

### Technicals

| Field | Source | License | Where it comes from | Production replacement |
|---|---|---|---|---|
| Daily OHLCV (5 years) | yfinance | 🟠 DEMO_ONLY | `Ticker.history(period='5y')` | Nanovest price feed (PRICE_PROVIDER=nanovest) or licensed exchange data (e.g. Nasdaq / NYSE via a data vendor) |
| Indicators (SMA, RSI, MACD, Bollinger, ATR) | Calculated from prices | 🟠 DEMO_ONLY | `core/technicals.py` | Becomes Calculated with Nanovest prices |
| Support / resistance and pivots | Calculated from prices | 🟠 DEMO_ONLY | `core/technicals.py` | Becomes Calculated with Nanovest prices |
| Benchmarks (SPY, sector ETF) | yfinance | 🟠 DEMO_ONLY | `history('SPY'), config/sector_etfs.yaml` | Licensed index / ETF prices |
| Risk-free rate (13-week T-bill) | yfinance ^IRX | 🟠 DEMO_ONLY | `history('^IRX')` | US Treasury daily rates (treasury.gov, public domain) |
| Beta, volatility, drawdown, Sharpe | Calculated from prices | 🟠 DEMO_ONLY | `core/risk.py` | Becomes Calculated with licensed prices |

### Earnings

| Field | Source | License | Where it comes from | Production replacement |
|---|---|---|---|---|
| EPS estimate, reported EPS, surprise | yfinance (Finnhub fallback) | 🟠 DEMO_ONLY | `Ticker.get_earnings_dates; /stock/earnings` | Licensed estimates: LSEG I/B/E/S, FactSet Estimates, S&P Capital IQ, Zacks |
| Earnings dates and time (before open / after close) | yfinance | 🟠 DEMO_ONLY | `Ticker.get_earnings_dates` | Licensed earnings calendar: Wall Street Horizon, Nasdaq, Benzinga |
| Estimate revisions | yfinance | 🟠 DEMO_ONLY | `Ticker.eps_trend, eps_revisions` | Licensed estimates: LSEG I/B/E/S, FactSet Estimates, S&P Capital IQ, Zacks |
| Revenue estimates | Finnhub, yfinance | 🟠 DEMO_ONLY | `/calendar/earnings; Ticker.revenue_estimate` | Licensed estimates: LSEG I/B/E/S, FactSet Estimates, S&P Capital IQ, Zacks |
| 10-Q / 10-K / 8-K links | SEC EDGAR | 🟢 COMMERCIAL_OK | `submissions filings (8-K item 2.02)` | already licensed-safe |

### Dividends

| Field | Source | License | Where it comes from | Production replacement |
|---|---|---|---|---|
| Dividend history (per share) | yfinance | 🟠 DEMO_ONLY | `Ticker.dividends` | Licensed corporate-actions feed (e.g. Nasdaq, exchange data vendors); SEC 8-K/10-Q as cross-check |
| Next ex-dividend date | yfinance | 🟠 DEMO_ONLY | `Ticker.calendar['Ex-Dividend Date']` | Licensed corporate-actions feed (e.g. Nasdaq, exchange data vendors); SEC 8-K/10-Q as cross-check |
| Payout ratio | Calculated from SEC | 🔵 CALCULATED_SAFE | `dividends paid / net income (TTM)` | already licensed-safe |

### Ownership

| Field | Source | License | Where it comes from | Production replacement |
|---|---|---|---|---|
| Insiders % / institutions % | yfinance | 🟠 DEMO_ONLY | `Ticker.major_holders` | SEC 13F filings parsed directly (free, licensed-safe) or FactSet Ownership |
| Top institutional holders | yfinance | 🟠 DEMO_ONLY | `Ticker.institutional_holders` | SEC 13F filings parsed directly (free, licensed-safe) or FactSet Ownership |
| Insider transactions | yfinance | 🟠 DEMO_ONLY | `Ticker.insider_transactions` | SEC Form 4 filings parsed directly (free, licensed-safe) |
| Wall Street analysts' ratings | Finnhub, yfinance | 🟠 DEMO_ONLY | `/stock/recommendation; Ticker.recommendations` | Licensed analyst ratings: LSEG, FactSet, Benzinga, Zacks |
| Upgrades / downgrades | yfinance | 🟠 DEMO_ONLY | `Ticker.upgrades_downgrades` | Licensed analyst ratings: LSEG, FactSet, Benzinga, Zacks |
| Short interest | yfinance | 🟠 DEMO_ONLY | `Ticker.info shortPercentOfFloat, shortRatio` | FINRA / exchange short-interest files (licensed) |

### News

| Field | Source | License | Where it comes from | Production replacement |
|---|---|---|---|---|
| Company news | Finnhub (yfinance fallback) | 🟠 DEMO_ONLY | `/company-news; Ticker.news` | Licensed news API: Dow Jones, Reuters, Benzinga |
| SEC filings feed | SEC EDGAR | 🟢 COMMERCIAL_OK | `submissions filings` | already licensed-safe |

### Scorecard

| Field | Source | License | Where it comes from | Production replacement |
|---|---|---|---|---|
| Pillar scores, strengths and risks | Calculated (mixed inputs) | 🟠 DEMO_ONLY | `core/scorecard.py, config/scoring.yaml` | In safe mode only licensed-safe inputs are used |

---
73 fields: 21 COMMERCIAL_OK, 10 CALCULATED_SAFE, 42 DEMO_ONLY.
