# Build Spec: US Stock Analysis Dashboard (Nanovest Demo)

> How to use this file: save it in an empty project folder as `SPEC.md`. Then tell Claude Code:
> "Read SPEC.md fully. Build Phase 1 only. When done, show me how to run it and stop."
> After you check it works, say "Build Phase 2", and so on.

---

## 0. Instructions for Claude Code (read first)

- You are building a working demo of a per-symbol US stock analysis dashboard. The user is a beginner. Explain how to run things in simple steps.
- Build in the phases listed in Section 12. Do ONE phase at a time. At the end of each phase: run the app, run the tests, fix errors, then summarize what was built and what the user should check. Stop and wait.
- Before you write code that depends on a library's API (yfinance, Finnhub, SEC EDGAR), check the installed version's real function names and response shapes. Do not guess. If a function does not exist, find the correct one.
- Every data fetch can fail. Never let one failed field crash the page. Show "N/A" with a short reason (for example "Not reported by this company" or "Data source unavailable").
- Keep code clean and modular so Nanovest's engineers can reuse the data and calculation layers in the real app later.
- Write a `README.md` in simple language: what it is, how to install, how to run, how to add API keys, where each data field comes from.
- Never hardcode secrets. Use a `.env` file and provide `.env.example`.

---

## 1. Goal and context

- Nanovest is an investment app. We want a stock detail page similar to (or better than) Stockbit and Pluang for US stocks.
- The user types a ticker (for example `AAPL`) and gets a full dashboard: overview, price and technicals, earnings, financials, valuation, profitability, financial health, dividends, ownership, analyst sentiment, news.
- Purpose: help users understand a stock better so they can make more informed decisions. Show data, charts and plain-language explanations of what each number means.
- This is a DEMO for internal approval. It uses some data sources that are free for personal or demo use only. The code must make it easy to swap those sources for paid, licensed vendors later (see Section 9).
- Nanovest already has its own real-time price feed. In the demo, use yfinance for prices, but put prices behind a provider interface so Nanovest's feed can be plugged in later.

---

## 2. Hard rules

1. **No buy or sell recommendations.** Never show words like "Buy", "Sell", "Strong Buy" as OUR verdict. Our own scoring uses "Strong / Neutral / Weak" per category and lists "Strengths" and "Risks". (Showing third-party analyst ratings is fine if clearly labeled as "Wall Street analysts' ratings".)
2. **Disclaimer** visible on every page footer: "This information is for educational purposes only and is not investment advice. Past performance does not guarantee future results. Data may be delayed or inaccurate."
3. **Every metric shows its source and license tag** (see Section 9).
4. **Every metric has a tooltip** with: what it means (1 to 2 simple sentences), how it is calculated, and what is generally considered good or bad. Write these for beginners.
5. **Estimates are labeled as estimates.** Anything that uses assumptions (fair value, DCF) shows the assumptions and says "estimate, not a prediction".
6. Handle special cases without crashing:
   - Banks and insurers (for example JPM): no gross profit, no cost of revenue, EBITDA not meaningful. Show N/A with reason.
   - Companies with no dividend (for example TSLA): hide dividend charts and show "This company does not pay a dividend".
   - Negative earnings: P/E shows "N/A (negative earnings)", not a negative number.
   - Non-calendar fiscal years (for example NVDA, MSFT, AAPL): label quarters by fiscal quarter AND show the period end date.
   - Tickers with a dot or dash (for example BRK-B / BRK.B): normalize for each source.
   - Invalid ticker: friendly error message.

---

## 3. Tech stack and project structure

- Python 3.11+
- **Streamlit** for the demo UI
- **Plotly** for all charts (interactive, hover tooltips, consistent colors, dark and light friendly)
- **pandas, numpy** for calculations
- **requests** for HTTP
- **yfinance** (latest version) for demo-only data
- **Finnhub** free API (via `requests`) for demo-only data
- **SEC EDGAR** APIs (via `requests`) for commercial-safe fundamentals
- **FastAPI + uvicorn** to expose the same data as JSON endpoints (so the mobile app team can see how it would plug in)
- **diskcache** or **requests-cache** (or SQLite) for caching
- **pydantic** for data models
- **pytest** for tests
- Pin all versions in `requirements.txt`.

Suggested structure:

```
stock-dashboard/
  SPEC.md
  README.md
  requirements.txt
  .env.example
  config/
    settings.py            # env vars, cache TTLs, feature flags
    scoring.yaml           # all scorecard thresholds (editable by non-coders)
    sector_etfs.yaml       # sector -> ETF mapping (XLK, XLF, XLV, ...)
    xbrl_tags.yaml         # field -> list of XBRL tags in priority order
    glossary_en.yaml       # tooltips in English
    glossary_id.yaml       # tooltips in Bahasa Indonesia
  core/
    providers/
      base.py              # abstract interfaces: PriceProvider, FundamentalsProvider,
                           # EstimatesProvider, NewsProvider, OwnershipProvider
      sec_edgar.py         # commercial-safe
      yfinance_provider.py # demo-only
      finnhub_provider.py  # demo-only
      nanovest_price.py    # stub with TODOs for Nanovest's internal price API
    models.py              # pydantic models; every value carries source + license tag
    financials.py          # build quarterly/annual statements, derive Q4, TTM
    ratios.py              # valuation, profitability, health, dividend ratios
    technicals.py          # indicators, support/resistance, trend signals
    risk.py                # beta, volatility, drawdown, Sharpe
    earnings.py            # surprises, post-earnings reaction, estimate trends
    valuation.py           # history bands, Graham number, DCF, peer compare
    quality_scores.py      # Piotroski F-score, Altman Z-score
    scorecard.py           # pillar scores + strengths/risks text
    cache.py
  api/
    main.py                # FastAPI endpoints (Section 11)
  app/
    streamlit_app.py       # main page
    components/            # one file per tab + shared chart helpers
  tests/
```

---

## 4. Data sources and what to pull

Environment variables (`.env.example`):

```
SEC_USER_AGENT="CompanyName DemoApp contact@example.com"   # SEC requires a real contact
FINNHUB_API_KEY=""
PRICE_PROVIDER="yfinance"        # later: "nanovest"
PRODUCTION_SAFE_MODE="false"     # true = hide all DEMO_ONLY fields
LANGUAGE="en"                    # en or id
```

### 4.1 SEC EDGAR (free, license tag: COMMERCIAL_OK)

Rules: send the `User-Agent` header from `SEC_USER_AGENT` on every request. Stay under 10 requests per second. Cache heavily.

| Endpoint | What to pull |
|---|---|
| `https://www.sec.gov/files/company_tickers.json` | Ticker to CIK mapping (pad CIK to 10 digits) |
| `https://data.sec.gov/submissions/CIK##########.json` | Company name, SIC code and description, exchange, fiscal year end, addresses, website if present, list of recent filings (form type, filing date, report date, accession number, primary document) |
| `https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json` | All reported financial facts (us-gaap and dei) |
| Filing documents (built from accession number) | Links to 10-K, 10-Q, 8-K (earnings press releases are usually 8-K Exhibit 99.1) |
| Form 4 filings (from submissions list) | Insider transactions (if time allows; otherwise use yfinance insider data in demo) |

Use EDGAR as the **primary** source for: income statement, balance sheet, cash flow, GAAP EPS, shares outstanding, dividends per share declared, filing history, company profile basics.

### 4.2 yfinance (free, license tag: DEMO_ONLY)

| Function / attribute | What to pull |
|---|---|
| `Ticker.history()` | Daily OHLCV, at least 5 years (for technicals, valuation history, risk). Also weekly for beta. |
| `Ticker.info` | Long business summary, sector, industry, employees, website, CEO (from officers), market cap, shares, forward P/E, PEG, short % of float, short ratio, analyst target prices, recommendation mean |
| `Ticker.quarterly_income_stmt`, `income_stmt`, `quarterly_balance_sheet`, `balance_sheet`, `quarterly_cashflow`, `cashflow` | Backup and cross-check for EDGAR. Also "Normalized EBITDA" if available |
| `Ticker.get_earnings_dates()` / `earnings_dates` | Past and upcoming earnings dates, EPS estimate, reported EPS, surprise % |
| `Ticker.earnings_estimate`, `revenue_estimate`, `eps_trend`, `eps_revisions`, `growth_estimates` | Forward estimates and how they changed over 7/30/60/90 days |
| `Ticker.calendar` | Next earnings date, ex-dividend date |
| `Ticker.recommendations`, `upgrades_downgrades`, `analyst_price_targets` | Analyst rating counts by month, rating changes, price target low/mean/high |
| `Ticker.dividends`, `Ticker.splits` | Dividend history, split history |
| `Ticker.institutional_holders`, `major_holders`, `mutualfund_holders`, `insider_transactions` | Ownership data |
| `Ticker.news` | News headlines, publisher, link, time, thumbnail |
| `yf.download("SPY")`, sector ETF, `^IRX` | Benchmark prices, sector ETF prices, risk-free rate (13-week T-bill) |

Important: yfinance is unofficial and can break or rate limit. Wrap every call in try/except with retry and backoff, cache results, and fail per field, never per page. Verify attribute names against the installed version.

Note on Adjusted EPS: the "reported EPS" in yfinance and Finnhub earnings data is usually the adjusted (non-GAAP) EPS that analysts compare against. Label it "Reported EPS (usually adjusted)" and show GAAP diluted EPS from EDGAR next to it.

### 4.3 Finnhub free API (free tier, license tag: DEMO_ONLY)

Base URL `https://finnhub.io/api/v1`, token from `FINNHUB_API_KEY`. Respect the free rate limit (about 60 calls/minute). If no key is set, skip Finnhub and use yfinance only.

| Endpoint | What to pull |
|---|---|
| `/stock/profile2` | Logo URL, company website, industry, IPO date |
| `/stock/peers` | Peer tickers (for peer comparison) |
| `/stock/earnings` | Actual vs estimate EPS and surprise (cross-check with yfinance) |
| `/calendar/earnings` | Upcoming earnings date and estimates |
| `/stock/recommendation` | Analyst rating trends by month |
| `/company-news` | Company news for the last 30 days |
| `/stock/metric?metric=all` | Backup for ratios, 52-week high/low, beta |

### 4.4 Nanovest price provider (stub, license tag: COMMERCIAL_OK)

Create `core/providers/nanovest_price.py` that implements `PriceProvider` with clear TODOs (`get_quote(symbol)`, `get_history(symbol, start, end, interval)`). Switching `PRICE_PROVIDER=nanovest` must be the only change needed later.

### 4.5 Source priority

For each field, define a priority list in code, for example:
- Financial statements: EDGAR, then yfinance
- Price: PRICE_PROVIDER, then yfinance
- Earnings estimates: yfinance, then Finnhub
- News: Finnhub, then yfinance
- Peers: Finnhub, then same SIC code companies from EDGAR

When two sources disagree on a financial statement value by more than 2%, log it (a "data quality" panel in a debug expander is a nice extra).

---

## 5. EDGAR field mapping (put in `config/xbrl_tags.yaml`)

Try tags in order. Use the first one that has data for the period. Companies use different tags.

| Field | XBRL tags (priority order) |
|---|---|
| Revenue | `Revenues`, `RevenueFromContractWithCustomerExcludingAssessedTax`, `RevenueFromContractWithCustomerIncludingAssessedTax`, `SalesRevenueNet` |
| Cost of revenue | `CostOfRevenue`, `CostOfGoodsAndServicesSold`, `CostOfGoodsSold` |
| Gross profit | `GrossProfit` (else Revenue minus Cost of revenue) |
| R&D | `ResearchAndDevelopmentExpense` |
| SG&A | `SellingGeneralAndAdministrativeExpense` |
| Operating income | `OperatingIncomeLoss` |
| Interest expense | `InterestExpense`, `InterestExpenseNonoperating` |
| EBT (pretax income) | `IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest`, `IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments` |
| Income tax | `IncomeTaxExpenseBenefit` |
| Net income | `NetIncomeLoss`, `ProfitLoss` |
| EPS basic / diluted | `EarningsPerShareBasic`, `EarningsPerShareDiluted` |
| Diluted shares (weighted) | `WeightedAverageNumberOfDilutedSharesOutstanding` |
| Shares outstanding | `dei:EntityCommonStockSharesOutstanding`, `CommonStockSharesOutstanding` |
| D&A | `DepreciationDepletionAndAmortization`, `DepreciationAndAmortization`, `DepreciationAmortizationAndAccretionNet` |
| Total assets | `Assets` |
| Current assets | `AssetsCurrent` |
| Total liabilities | `Liabilities` (else Assets minus Equity incl. noncontrolling interest) |
| Current liabilities | `LiabilitiesCurrent` |
| Cash | `CashAndCashEquivalentsAtCarryingValue`, `CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents` |
| Short-term investments | `ShortTermInvestments`, `MarketableSecuritiesCurrent` |
| Inventory | `InventoryNet` |
| Receivables | `AccountsReceivableNetCurrent` |
| Short-term debt | `DebtCurrent`, `LongTermDebtCurrent`, `ShortTermBorrowings`, `CommercialPaper` |
| Long-term debt | `LongTermDebtNoncurrent`, `LongTermDebt` |
| Shareholders' equity | `StockholdersEquity`, `StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest` |
| Retained earnings | `RetainedEarningsAccumulatedDeficit` |
| Operating cash flow | `NetCashProvidedByUsedInOperatingActivities` |
| Capex | `PaymentsToAcquirePropertyPlantAndEquipment`, `PaymentsToAcquireProductiveAssets` |
| Dividends paid | `PaymentsOfDividends`, `PaymentsOfDividendsCommonStock` |
| Buybacks | `PaymentsForRepurchaseOfCommonStock` |
| Dividends per share | `CommonStockDividendsPerShareDeclared`, `CommonStockDividendsPerShareCashPaid` |

Parsing rules (important):
1. **Duration vs instant facts.** Income and cash flow items are durations (have start and end dates). Balance sheet items are instants (end date only).
2. **Quarterly values.** Keep duration facts of about 80 to 100 days as quarters. Annual facts are about 350 to 380 days.
3. **Derive Q4.** 10-K reports the full year, not Q4. Q4 = full year minus (Q1 + Q2 + Q3). Mark derived values as "derived". Do NOT derive Q4 for EPS by subtraction if share counts changed a lot; instead compute Q4 EPS = Q4 net income / Q4 diluted shares when possible, and mark it.
4. **Cash flow in 10-Q is year-to-date.** Q2 cash flow in the filing is 6 months. Derive single quarters by subtracting the previous year-to-date value.
5. **Duplicates and restatements.** The same period appears in many filings. Prefer facts that have a `frame` value; otherwise use the most recently filed value for that period.
6. Keep at least the last 12 quarters and 5 fiscal years (more if available).
7. Store values in a tidy table: `field, period_end, period_type (Q/FY), fiscal_year, fiscal_quarter, value, unit, source, derived (bool), license_tag`.

---

## 6. Calculations

TTM = sum of the last 4 quarters (income and cash flow items). Balance sheet items use the latest quarter. "Average" equity or assets = average of start and end of the period.

### 6.1 Income statement metrics
- Gross profit (if missing) = Revenue minus Cost of revenue
- **EBITDA** = Operating income + D&A (label "calculated"). Also show yfinance "Normalized EBITDA" if available (DEMO_ONLY)
- EBT = pretax income
- Gross margin, operating margin, EBITDA margin, net margin, EBT margin = metric / revenue
- Revenue growth: quarter over quarter (QoQ) and year over year (YoY, same quarter last year)
- EPS growth YoY
- 3-year and 5-year CAGR for revenue, net income, EPS, free cash flow
- Expense breakdown: COGS, R&D, SG&A as % of revenue
- Effective tax rate = income tax / EBT

### 6.2 Balance sheet metrics
- Net debt = total debt minus cash and short-term investments
- Book value per share = equity / shares outstanding
- Current ratio = current assets / current liabilities
- Quick ratio = (current assets minus inventory) / current liabilities
- Debt to equity = total debt / equity
- Debt to EBITDA (TTM)
- Interest coverage = operating income / interest expense

### 6.3 Cash flow metrics
- Free cash flow (FCF) = operating cash flow minus capex
- FCF margin = FCF / revenue
- FCF per share
- Cash conversion (earnings quality) = operating cash flow / net income
- Shareholder return = dividends paid + buybacks

### 6.4 Valuation (use price from PRICE_PROVIDER)
- Market cap = price × shares outstanding
- Enterprise value (EV) = market cap + total debt minus cash and short-term investments
- P/E (TTM) = price / TTM diluted EPS (N/A if EPS is zero or negative)
- Forward P/E = price / next fiscal year EPS estimate (DEMO_ONLY)
- PEG = P/E / expected EPS growth % (DEMO_ONLY, uses estimates)
- P/S = market cap / TTM revenue
- P/B = market cap / equity
- EV/EBITDA = EV / TTM EBITDA
- EV/Revenue
- P/FCF and FCF yield = FCF TTM / market cap
- Earnings yield = 1 / P/E
- **Valuation history:** for each trading day in the last 5 years, compute P/E, P/S, EV/EBITDA using the TTM values known at that date (use filing date, not period end, to avoid look-ahead). Output: current value, 5-year median, 5-year min/max, and percentile (for example "P/E is higher than 80% of the last 5 years").
- **Peer comparison:** same ratios for up to 8 peers (Finnhub peers or same SIC). Show peer median.
- **Graham number** = sqrt(22.5 × EPS × book value per share) (only if both positive). Label "classic formula, estimate".
- **Simple DCF (estimate):** 5-year FCF projection. Defaults: growth = min(analyst growth estimate or 3-year FCF CAGR, 20%), discount rate = 10%, terminal growth = 2.5%. User can change all three with sliders. Output fair value per share and range (bear/base/bull = growth -5pp, base, +5pp). Big label: "Estimate based on assumptions. Not a prediction."
- **Analyst price target upside** = (mean target / price) minus 1 (DEMO_ONLY)

### 6.5 Profitability
- ROE = net income TTM / average equity
- ROA = net income TTM / average total assets
- ROIC = NOPAT / (debt + equity minus cash), where NOPAT = operating income × (1 minus effective tax rate)
- DuPont: ROE = net margin × asset turnover × equity multiplier (show all three)
- Margin trends over 12 quarters

### 6.6 Dividends
- Dividend per share TTM (from yfinance dividends history, cross-check EDGAR)
- Dividend yield TTM = DPS TTM / price
- Payout ratio = dividends TTM / net income TTM (also FCF payout = dividends / FCF)
- Dividend growth CAGR 3y and 5y
- Consecutive years of dividend growth
- Yield history (5 years) and 5-year average yield
- Next ex-dividend date (DEMO_ONLY)

### 6.7 Quality and risk scores
- **Piotroski F-score (0 to 9):** compute all 9 tests from EDGAR annual data (positive ROA, positive operating cash flow, ROA improving, OCF > net income, leverage falling, current ratio rising, no new shares issued, gross margin rising, asset turnover rising). Show each test as pass/fail with a plain explanation.
- **Altman Z-score:** standard formula for non-financial companies. Show zone: Safe (> 2.99), Grey (1.81 to 2.99), Distress (< 1.81). Skip for banks and insurers with reason.

### 6.8 Technicals (from daily prices)
- SMA 20, 50, 200; EMA 12, 26
- RSI (14)
- MACD (12, 26, 9) with signal and histogram
- Bollinger Bands (20, 2)
- ATR (14)
- Average volume (20 and 50 day), volume vs average
- 52-week high and low, % from each
- Trend signals (as facts, not advice): price above or below SMA 50 and SMA 200; golden cross or death cross in the last 60 days (with date); RSI above 70 "overbought zone" or below 30 "oversold zone"; MACD crossover with date
- **Support and resistance algorithm:**
  1. Find swing highs and swing lows using a window of 5 bars on each side, over the last 1 year of daily data (also offer 6 months and 2 years).
  2. Cluster levels that are within 0.5 × ATR (or 1.5% of price, whichever is larger) of each other. The cluster level = average price.
  3. Strength = number of touches, with extra weight for recent touches and high-volume touches.
  4. Keep the 3 strongest levels below the current price (support) and 3 above (resistance).
  5. Also compute classic pivot points from the previous week (P, S1, S2, R1, R2).
  6. Show distance from current price to nearest support and resistance in %.
  7. Label: "Support and resistance are areas where price reacted before. They are not guarantees."

### 6.9 Risk and performance
- Returns: 1D, 1W, 1M, 3M, 6M, YTD, 1Y, 3Y, 5Y
- Relative performance vs SPY and vs sector ETF for the same periods
- Beta vs SPY (2 years of weekly returns)
- Annualized volatility (1 year daily)
- Max drawdown (1Y, 5Y) and current drawdown from all-time high in the data
- Sharpe ratio (1Y) using `^IRX` as risk-free rate
- Monthly returns table (for seasonality heatmap)

### 6.10 Earnings analytics
- For each past quarter (up to 12): EPS estimate, reported EPS, surprise %, beat/miss/inline (inline = within ±1%)
- Revenue estimate vs actual where available
- Beat rate (last 8 and 12 quarters)
- **Post-earnings price reaction:** price change from the close before earnings to the close 1 day and 5 days after (handle before-open vs after-close announcements: if time unknown, use the first close after the date). Average absolute move = "typical earnings move".
- Estimate revisions: how the current quarter and next year EPS estimates changed over 7, 30, 60, 90 days (from eps_trend), count of upward vs downward revisions
- Upcoming earnings: date, EPS estimate, revenue estimate, days until

---

## 7. Scorecard and plain-language insights

Seven pillars, each scored 0 to 100, shown as "Strong" (70+), "Neutral" (40 to 69), "Weak" (below 40). All thresholds live in `config/scoring.yaml` so the team can adjust without coding.

| Pillar | Inputs (example rules, put real thresholds in YAML) |
|---|---|
| Valuation | P/E vs own 5y median, P/E vs peer median, EV/EBITDA vs peers, FCF yield, PEG |
| Growth | Revenue YoY, EPS YoY, 3y revenue CAGR, forward growth estimate |
| Profitability | Net margin, ROE, ROIC, margin trend (rising or falling) |
| Financial health | Debt to equity, current ratio, interest coverage, Altman Z, net cash or net debt |
| Earnings quality | Piotroski F-score, cash conversion, beat rate, estimate revisions direction |
| Momentum | Price vs SMA 50/200, 6M relative strength vs SPY, distance from 52w high |
| Dividend | Yield vs 5y average, payout ratio safety, growth streak (show "Not applicable" if no dividend; exclude from overall) |

- Missing inputs: score the pillar with available inputs and show "based on X of Y metrics".
- **Strengths and Risks:** auto-generate up to 5 bullet points each, in simple language, from rules. Examples:
  - "Revenue grew 15% compared with the same quarter last year."
  - "P/E is higher than 85% of the last 5 years, so the stock is priced more expensively than usual."
  - "The company beat EPS estimates in 7 of the last 8 quarters."
  - "Debt is 2.5× its yearly EBITDA, which is higher than its peers."
- Also show third-party analyst consensus separately, clearly labeled as "Wall Street analysts' view" (DEMO_ONLY).
- Show all text in English or Bahasa Indonesia based on the LANGUAGE setting (glossary and insight templates in YAML).

---

## 8. Dashboard layout and charts

General chart rules: Plotly, consistent color system (green for positive/beat, red for negative/miss, one neutral color for the stock, gray for benchmark), hover shows exact values with units, no chart junk, readable on a phone width. Every chart has a short title that says what to look at, and a source + license badge. Quarterly/Annual toggle wherever relevant. Each table has "Download CSV".

### Header (always visible)
- Logo, company name, ticker, exchange, sector, industry
- Price, change today (from PRICE_PROVIDER), market cap
- 52-week range bar showing where current price sits
- Next earnings date (with countdown)
- Overall scorecard pills (7 pillars, colored)
- Data freshness ("Financials as of Q3 FY2026, filed 2026-10-30")

### Tab 1: Summary
- Radar chart of the 7 pillar scores
- Strengths and Risks lists
- Key stats cards: P/E, P/S, EV/EBITDA, revenue growth YoY, net margin, ROE, debt to equity, dividend yield, beta (each with tooltip and color vs peers)
- Mini 1-year price chart with nearest support and resistance lines
- Analyst consensus gauge and price target range bar (low, mean, high vs current price)

### Tab 2: Price and Technicals
- Candlestick chart with volume bars (range selector: 1M, 3M, 6M, 1Y, 3Y, 5Y)
- Overlays (toggle): SMA 20/50/200, Bollinger Bands, support and resistance lines with strength labels, pivot points
- Earnings date markers on the price chart (hover shows surprise %)
- RSI subplot with 30/70 lines
- MACD subplot
- Trend signals table (facts with dates)
- Relative performance line chart: stock vs SPY vs sector ETF, rebased to 100
- Returns table (1D to 5Y) vs SPY and sector
- Drawdown chart (underwater chart)
- Monthly returns heatmap (years × months)
- Risk cards: beta, volatility, max drawdown, Sharpe

### Tab 3: Earnings
- **EPS Actual vs Expected:** grouped bar chart per quarter (up to 12), actual bar colored green (beat) or red (miss), surprise % label on top
- Revenue actual vs expected (if available)
- Beat rate stat card
- **Post-earnings price reaction:** bar chart of 1-day move after each earnings, plus "typical earnings move" stat
- GAAP EPS (EDGAR) vs reported/adjusted EPS line chart
- Upcoming earnings card: date, EPS estimate, revenue estimate, number of analysts
- Estimate revisions chart (current Q and next FY estimate over 90/60/30/7 days ago and now)
- Past earnings reports table: quarter, date, EPS estimate, EPS actual, surprise %, revenue, links to 10-Q/10-K/8-K press release on SEC

### Tab 4: Financials
Sub-tabs: Income Statement, Balance Sheet, Cash Flow. Quarterly/Annual toggle.
- **Income:**
  - Combo chart: revenue bars + net margin line (secondary axis)
  - Grouped bars: revenue, gross profit, EBITDA, EBT, net income per quarter
  - Margin trend lines: gross, operating, EBITDA, net
  - Growth bars: revenue YoY % and EPS YoY %
  - Expense breakdown stacked bars (COGS, R&D, SG&A as % of revenue)
  - Full income statement table (derived values marked with a small icon)
- **Balance sheet:**
  - Stacked bars: total assets vs liabilities + equity
  - Cash vs total debt bars with net debt line
  - Current ratio and debt to equity lines
  - Full table
- **Cash flow:**
  - Operating cash flow, capex, FCF bars
  - FCF vs net income lines (earnings quality)
  - Shareholder returns stacked bars (dividends + buybacks)
  - Full table

### Tab 5: Valuation
- Ratio cards with three comparisons each: now vs 5y median vs peer median
- **P/E history band chart:** P/E over 5 years with median line and ±1 standard deviation band
- P/S and EV/EBITDA history lines
- Percentile bars ("cheaper or more expensive than its own history")
- Peer comparison table (ticker, market cap, P/E, P/S, EV/EBITDA, revenue growth, net margin, ROE) and a bar chart for a selected metric
- Fair value section: Graham number, DCF with 3 sliders and bear/base/bull result bar, analyst targets. Price vs these values on one horizontal chart. Big "estimate" label.

### Tab 6: Profitability and Financial Health
- ROE, ROA, ROIC lines (quarterly TTM)
- DuPont breakdown chart
- Piotroski F-score card with 9 pass/fail checks
- Altman Z-score gauge with zones
- Interest coverage and debt to EBITDA lines

### Tab 7: Dividends (hide content if no dividend)
- Cards: yield TTM, payout ratio, FCF payout, 5y dividend CAGR, growth streak, next ex-dividend date
- Dividend per share bars by year
- Yield history line with 5y average line
- Payout ratio history line

### Tab 8: Ownership and Sentiment
- Major holders breakdown (insiders %, institutions %) donut chart
- Top 10 institutional holders table
- Insider transactions table and monthly net buy/sell bar chart
- Analyst recommendations stacked bar by month (labeled "Wall Street analysts' ratings")
- Recent upgrades and downgrades list
- Short interest cards: % of float, days to cover

### Tab 9: News and Filings
- News list: date, source, headline (link opens original), thumbnail
- Filter: last 7 / 30 days
- SEC filings feed: latest 8-K, 10-Q, 10-K, Form 4 with links

### Tab 10: Company Profile
- Business description (short version first, "read more" for full)
- Sector, industry, SIC, employees, HQ, website, CEO, fiscal year end, IPO date
- Peer list (clickable to load that ticker)

### Sidebar
- Ticker input with search (from SEC ticker list)
- Recently viewed tickers
- Language toggle (EN / ID)
- PRODUCTION_SAFE_MODE toggle
- Refresh data button (clears cache for this ticker)

---

## 9. Data license tags and production-safe mode

Every value in `core/models.py` carries:
- `source`: "SEC EDGAR", "yfinance", "Finnhub", "Nanovest", "Calculated"
- `license_tag`: one of
  - `COMMERCIAL_OK`: SEC EDGAR, Nanovest price feed
  - `CALCULATED_SAFE`: calculated only from COMMERCIAL_OK inputs
  - `DEMO_ONLY`: from yfinance or Finnhub free, or calculated using any DEMO_ONLY input
- `derived`: true if we computed it (for example Q4 values)
- `as_of`: date of the data

UI:
- Small badge next to each metric/chart: green "Licensed-safe", blue "Calculated", orange "Demo data".
- When `PRODUCTION_SAFE_MODE=true`: hide every DEMO_ONLY item and show a placeholder "Requires a licensed data provider". This lets the team see exactly what the app looks like with only free commercial-safe data, and what a paid vendor would add.
- Generate a "Data coverage report" page listing every field, its source, license tag, and whether it loaded for the current ticker.

---

## 10. Caching, performance, errors

- Cache TTLs: price history 15 minutes (demo), quote 1 minute, EDGAR companyfacts 24 hours, submissions 6 hours, estimates 6 hours, news 30 minutes, profile 7 days, SEC ticker list 7 days.
- Load the header and summary first; load heavy tabs lazily.
- Fetch independent sources in parallel (thread pool), respecting rate limits.
- Target: first load under 10 seconds, cached load under 2 seconds.
- Logging: one log line per source call with time taken and success/failure.
- If a source is down, show what is available and a small warning banner.

---

## 11. API (FastAPI)

Expose the same core functions as JSON so the mobile team can see the contract:
- `GET /stocks/{ticker}/summary` (header + scorecard + key stats + strengths/risks)
- `GET /stocks/{ticker}/financials?period=quarterly|annual&statement=income|balance|cashflow`
- `GET /stocks/{ticker}/ratios`
- `GET /stocks/{ticker}/valuation`
- `GET /stocks/{ticker}/earnings`
- `GET /stocks/{ticker}/technicals?range=1y`
- `GET /stocks/{ticker}/dividends`
- `GET /stocks/{ticker}/ownership`
- `GET /stocks/{ticker}/news`
- `GET /stocks/{ticker}/profile`
- `GET /coverage/{ticker}` (data coverage report)
Every value includes `source`, `license_tag`, `as_of`. Respect PRODUCTION_SAFE_MODE. Auto-generated OpenAPI docs at `/docs`.

---

## 12. Build phases and acceptance criteria

Test tickers for every phase: **AAPL** (non-calendar FY, dividend), **MSFT**, **NVDA** (non-calendar FY), **KO** (dividend aristocrat), **TSLA** (no dividend), **JPM** (bank), **BRK-B** (special ticker), **a small cap with losses** (pick one, for example a current unprofitable small cap).

**Phase 1: Foundation**
- Project structure, requirements, `.env.example`, settings, cache, logging
- Provider interfaces + SEC EDGAR client (ticker to CIK, submissions, companyfacts) + yfinance + Finnhub clients + Nanovest stub
- Streamlit shell: sidebar, header, Company Profile tab, disclaimer footer, license badges
- Done when: typing any test ticker shows header and profile without errors; invalid ticker shows a friendly message

**Phase 2: Financial statements**
- XBRL mapping, quarterly/annual builder, Q4 derivation, YTD cash flow fix, dedupe, TTM
- Financials tab with all charts and tables
- Unit tests for Q4 derivation and YTD subtraction
- Done when: AAPL quarterly revenue and net income match Apple's reported numbers for the last 4 quarters (cross-check with yfinance within 2%); JPM shows N/A for gross profit with reason

**Phase 3: Ratios, valuation, profitability, health**
- All calculations in 6.1 to 6.5 and 6.7
- Valuation history (no look-ahead), peers, Graham, DCF sliders
- Valuation tab and Profitability/Health tab
- Unit tests for every formula with small hand-made examples
- Done when: ratios for AAPL are within reasonable range of yfinance values; negative EPS shows N/A for P/E

**Phase 4: Price, technicals, risk**
- Indicators, support/resistance algorithm, pivots, trend signals, risk metrics, relative performance
- Price and Technicals tab
- Unit tests for RSI, MACD, SMA, and support/resistance on a synthetic price series
- Done when: chart loads with toggles; support/resistance lines look sensible on AAPL and TSLA

**Phase 5: Earnings**
- Surprises, beat rate, post-earnings reaction, estimate revisions, upcoming earnings, filing links
- Earnings tab
- Done when: AAPL shows at least 4 quarters of actual vs expected with correct beat/miss colors

**Phase 6: Dividends, ownership, sentiment, news**
- Dividends tab, Ownership and Sentiment tab, News and Filings tab
- Done when: KO shows full dividend history and growth streak; TSLA shows "no dividend" message

**Phase 7: Scorecard, summary, language**
- `scoring.yaml`, pillar scores, strengths/risks generator, Summary tab, radar chart
- English and Bahasa Indonesia glossary and insight templates
- Done when: every test ticker shows a scorecard with explanations and no buy/sell wording anywhere

**Phase 8: API, production-safe mode, polish**
- FastAPI endpoints, PRODUCTION_SAFE_MODE behavior, data coverage report page
- Performance pass (parallel fetch, lazy tabs), full test run, README with screenshots
- Done when: `/docs` works, safe mode hides all orange-badge items, all tests pass

---

## 13. Final deliverables

1. Working Streamlit demo (`streamlit run app/streamlit_app.py`)
2. Working FastAPI (`uvicorn api.main:app`)
3. Tests passing (`pytest`)
4. `README.md` for beginners
5. `DATA_SOURCES.md`: table of every field, source, license tag, and which paid vendor endpoint would replace each DEMO_ONLY field
6. Short list of known limitations

---

## 14. Phase 9: Nanovest app UI simulation (mobile prototype)

### 14.1 Goal
- Build a clickable mobile prototype that looks and feels like the Nanovest app's US stock asset page, with the new analysis features added into it.
- Purpose: show managers, product and design teams what the feature would look like inside the real app.
- This is an **internal prototype only**. Run it locally. Never deploy it to a public URL.
- It does NOT replace the real app code. The real app team will rebuild it in their own tech stack.

### 14.2 Design inputs (provided by the user in the `design/` folder)

```
design/
  nanovest-screens/      # screenshots of the current Nanovest stock asset page, numbered in scroll order
                         # e.g. 01-top.png, 02-chart.png, 03-about.png, 10-tab-news.png, 20-dark-mode.png
  assets/                # Nanovest logo, icons, fonts (only use brand files from this folder)
  design-tokens.md       # colors (hex), fonts, font sizes, corner radius, spacing (if available)
  notes.md               # how things behave: taps, swipes, bottom sheets, what each button does
  reference-other-apps/  # optional: screenshots of other apps for FEATURE ideas only, never copy their look
```

Rules for using the inputs:
- The Nanovest screenshots are the source of truth for look and feel.
- If `design-tokens.md` exists, its values win over what you guess from screenshots.
- If something is not visible in the screenshots, follow the same style as the closest existing element. List every guess you made in `design/UI_ANALYSIS.md`.
- Do not copy the visual design of other apps. Use them only to understand which features exist.

### 14.3 Tech stack
- New folder `mobile-ui/`
- React + Vite + TypeScript + Tailwind CSS
- Charts:
  - Price and candlestick charts: **TradingView Lightweight Charts** (open source, keep the required attribution)
  - Bars, lines, radar, gauges: **Recharts**
- Data: call the FastAPI from Phase 8 (`api/main.py`). Enable CORS for the local dev server. All API URLs in one config file.
- Also include a **mock data mode** (JSON files for AAPL, KO, TSLA, JPM) so the prototype works even if the API or data sources are down during a meeting.
- Show the page inside a **phone frame** at 390 × 844 on desktop. On a real phone (opened over the local network), fill the screen.

### 14.4 Page structure

Keep the existing Nanovest page exactly as it is in the screenshots (header, price, chart, Buy/Sell buttons, existing sections). Then add the new analysis content in the most natural place, following the app's existing patterns (tabs, sections, or "See more" pages). Propose the placement in `UI_ANALYSIS.md` before building.

Mobile priority (phones are small, do NOT show all 50 desktop charts on one screen):

1. **Top (always visible):** existing Nanovest header and price. Add next earnings date chip.
2. **Analysis summary card:** 7 scorecard pills (Strong / Neutral / Weak), top 3 Strengths and top 3 Risks, "See full analysis" link.
3. **Key stats:** horizontal scroll cards (P/E, P/S, EV/EBITDA, revenue growth, net margin, ROE, debt to equity, dividend yield, beta). Tap a card for a bottom sheet with the explanation.
4. **Sections or tabs** (follow the app's existing style):
   - Overview: price chart with support/resistance toggle, returns vs S&P 500
   - Earnings: EPS actual vs expected bars, beat rate, typical move after earnings, upcoming earnings
   - Financials: revenue + net income bars, margin lines, Quarterly/Annual switch, "See full statement" page with horizontally scrollable table
   - Valuation: P/E history band, now vs history vs peers, fair value estimate
   - Health: Piotroski, Altman Z, debt and cash
   - Dividends: hidden if no dividend
   - Technicals: RSI, MACD, signals list
   - Analysts and Ownership
   - News and Filings
   - About the company
5. **Footer:** disclaimer (Section 2).

Mobile patterns to use:
- Bottom sheets for tooltips and explanations (tap the ⓘ icon)
- Segmented controls for Quarterly/Annual and time ranges
- Skeleton loaders while data loads
- Friendly empty and N/A states with the reason
- Tap on a chart to see the exact value (no hover on phones)
- Charts must be readable at 390px wide: max 8 to 12 bars, short labels, large tap targets

### 14.5 Prototype rules
- Buy and Sell buttons are visual only. Tapping them shows "Prototype only".
- No buy/sell verdict from us anywhere (Section 2 rule 1 still applies).
- License badges (green / blue / orange) are hidden by default. Add a hidden "Data badges" toggle (for example in a debug menu) to show them.
- Respect PRODUCTION_SAFE_MODE from the API: hidden fields show "Requires licensed data provider".
- Language toggle EN / ID, using the same glossary files.
- Support dark mode if the screenshots show the app has it.
- Show numbers in the same format and currency style as the Nanovest screenshots.

### 14.6 Build steps (do one, then stop and wait for the user)

**9a. Analyze the design (no app code yet)**
- Look at every image in `design/nanovest-screens/` and read `design-tokens.md` and `notes.md`.
- Write `design/UI_ANALYSIS.md` with: color palette (hex), fonts and sizes, spacing, corner radius, shadows, icon style, list of components (cards, tabs, buttons, chips, bottom sheets), navigation patterns, and a proposed placement of the new analysis sections (with a simple text wireframe).
- List everything you were unsure about. Stop and wait for the user to confirm or correct.

**9b. Rebuild the existing page (mock data)**
- Build the current Nanovest stock page as close to the screenshots as possible, with mock data, no new features yet.
- Take screenshots of the prototype with Playwright at 390 × 844 and compare them side by side with the reference screenshots. List differences and fix them. Repeat up to 3 rounds.
- Save comparison images in `design/compare/`. Stop and show the user.

**9c. Add the analysis features (real API)**
- Add the new sections in the agreed placement, connected to the FastAPI, with mock data mode as fallback.
- Test with AAPL, KO, TSLA, JPM, BRK-B.

**9d. Polish**
- Loading states, errors, empty states, dark mode, EN / ID, tap interactions, performance (first screen under 3 seconds with cache).
- Final Playwright screenshots of every section saved in `design/final/` for presentations.
- Update README: how to run the API and the prototype together, and how to open it on a phone on the same Wi-Fi.

### 14.7 Done when
- On a phone-sized screen, the page looks like it belongs in the Nanovest app.
- All new sections load for the test tickers, with N/A states where data is missing.
- Works in mock data mode with the API turned off.
- No buy/sell wording from us, disclaimer visible, Buy/Sell buttons are non-functional.

