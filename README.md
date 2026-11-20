# US Stock Analysis Dashboard (Nanovest demo)

A demo web page where you type a US stock ticker (for example `AAPL`) and see
information about the company. It is built in phases. The full plan is in `SPEC.md`.

**Status: Phases 1 to 7 are done.**
- **Scorecard:** 7 categories scored 0–100 and shown as Strong / Neutral / Weak pills in the header.
- **Summary** tab:
  - Radar chart of the 7 scores, plus automatic Strengths and Risks.
  - Key stats compared with peers.
  - 1-year chart with the nearest support and resistance.
  - Wall Street analysts' view, labeled as third-party.
- **Languages:** English and Bahasa Indonesia for tabs, sidebar, header, scorecard, strengths/risks and all tooltips.
- **Dividends** tab:
  - Yield, payout ratios, dividend growth and growth streak, next ex-dividend date.
  - Dividend history, yield over 5 years, payout ratio over time.
  - Companies without a dividend show "This company does not pay a dividend".
- **Ownership & Sentiment** tab:
  - Holder breakdown, top institutions, insider buying/selling.
  - Wall Street analysts' ratings (clearly labeled as third-party opinions) and recent rating changes.
  - Short interest.
- **News & Filings** tab: news from the last 7 or 30 days, and the SEC filings feed (8-K, 10-Q, 10-K, Form 4) with links.
- **Earnings** tab:
  - EPS actual vs expected for 12 quarters (beat / miss colors), beat rate, the price move after each report, GAAP vs adjusted EPS.
  - Revenue vs estimate, analyst estimate revisions, and the next earnings date with expectations.
  - A table with links to each quarter's SEC filings and press release.
- **Price & Technicals** tab:
  - Candlestick chart with volume, RSI and MACD; switchable overlays (moving averages, Bollinger Bands, support/resistance, pivot points, earnings dates).
  - Trend signals stated as facts.
  - Returns vs SPY and the sector ETF, beta, volatility, drawdowns, Sharpe ratio, monthly returns heatmap.
- Header: price, market cap, 52-week range, next earnings date, data freshness.
- **Company Profile** tab.
- **Financials** tab: income statement, balance sheet and cash flow, quarterly or annual, with charts and full tables.
- **Valuation** tab: ratios compared with the stock's own 5-year history and with peers, plus fair value estimates (Graham number, DCF with sliders, analyst targets).
- **Profitability & Health** tab: ROE / ROA / ROIC, DuPont breakdown, Piotroski F-score, Altman Z-score, debt ratios.

The other tabs say which phase will add them.

> This information is for educational purposes only and is not investment advice.

---

## 1. Install (one time)

You need Python 3.11 or newer. Open a terminal in this folder (in VS Code: **Terminal → New Terminal**) and run:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

## 2. Add your settings (API keys)

```powershell
Copy-Item env.template .env
code .env
```

In `.env`, fill in:

| Setting | What to put |
|---|---|
| `SEC_USER_AGENT` | App name + **your real email**. The SEC requires a contact email. |
| `FINNHUB_API_KEY` | Free key from https://finnhub.io (optional: leave empty to skip Finnhub) |
| `PRICE_PROVIDER` | `yfinance` for now (later `nanovest`) |
| `PRODUCTION_SAFE_MODE` | `true` hides all "Demo data" fields |
| `LANGUAGE` | `en` or `id` |

`.env` is private and is never shared (it is listed in `.gitignore`).
`env.template` (also copied as `.env.example`) is the safe, shareable template.

## 3. Run the app

```powershell
.venv\Scripts\python -m streamlit run app/streamlit_app.py
```

Your browser opens at http://localhost:8501. To stop the app, press **Ctrl+C** in the terminal.

## 4. Run the tests

```powershell
.venv\Scripts\python -m pytest              # fast tests, no internet needed
.venv\Scripts\python -m pytest -m network   # live tests against SEC / Yahoo / Finnhub
```

---

## Where each field comes from

Every value shows a colored badge. Hover over the badge to see its source and date.

| Badge | Meaning |
|---|---|
| 🟢 **Licensed-safe** | SEC EDGAR or the Nanovest price feed: OK for commercial use |
| 🔵 **Calculated** | We calculated it only from licensed-safe inputs |
| 🟠 **Demo data** | From yfinance or Finnhub free tier, or calculated using them. **Demo only**, must be replaced by a paid vendor before launch |

| Field | Source (priority order) | License |
|---|---|---|
| Company name, exchange, SIC code, HQ, fiscal year end, state of incorporation | SEC EDGAR submissions | Licensed-safe |
| Shares outstanding | SEC EDGAR (dei:EntityCommonStockSharesOutstanding) | Licensed-safe |
| Data freshness (latest 10-Q / 10-K) | SEC EDGAR | Licensed-safe |
| Price, change today, 52-week range | Price provider (yfinance now, Nanovest later) | Demo data (yfinance) |
| Market cap | Price × SEC shares; Yahoo's value for multi-class companies (e.g. BRK) | Demo data (price is demo) |
| Sector, industry, description, employees, CEO | yfinance | Demo data |
| Logo, IPO date, website | Finnhub (website: SEC first, then Finnhub, then yfinance) | Demo data |
| Next earnings date | yfinance, then Finnhub | Demo data |
| Peers | Finnhub, then companies in the same Yahoo industry | Demo data |

### Financial statements (Financials tab)

| What | Source | License |
|---|---|---|
| Income statement, balance sheet, cash flow | SEC EDGAR XBRL "companyfacts" (official 10-Q / 10-K numbers) | Licensed-safe |
| Q4 values, single-quarter cash flow, EBITDA, FCF, margins, growth, ratios | Calculated by us from SEC numbers (marked ✱ in tables) | Calculated |
| Backup if SEC has no data | yfinance statements (only ~5 quarters / 4 years) | Demo data |

How the numbers are built (all in `core/financials.py`, tag lists in `config/xbrl_tags.yaml`):
- **Tags:** companies use different XBRL tags for the same item and change them over the years. For each period we use the first tag in the list that has a value.
- **Q4:** companies don't file a Q4 report. Q4 = full year − 9-month year-to-date, or full year − Q1 − Q2 − Q3.
- **Cash flow:** 10-Q cash flow is year-to-date, so a single quarter = this year-to-date − the previous year-to-date.
- **Q4 EPS:** Q4 net income ÷ Q4 diluted shares, not a subtraction.
- **Restatements:** when a period was reported more than once, we use the value the SEC marks as best for that period, otherwise the most recently filed one.
- **Data quality check:** the last 4 quarters of revenue, net income, operating cash flow and total assets are compared with yfinance. Differences above 2% are logged and listed at the bottom of the Financials tab.
- **Banks and insurers** (e.g. JPM, BRK.B): gross profit, EBITDA, current ratio and similar items show N/A with the reason.

### Ratios, valuation and scores (Valuation and Profitability & Health tabs)

| What | Inputs | License |
|---|---|---|
| ROE, ROA, ROIC, margins, debt ratios, CAGR, Piotroski F-score | SEC financial statements only | Calculated |
| P/E, P/S, P/B, EV/EBITDA, FCF yield, valuation history, Altman Z | SEC statements + **price** (yfinance now) | Demo data (becomes "Calculated" with the Nanovest price feed) |
| Forward P/E, PEG, analyst targets, DCF default growth | yfinance analyst estimates | Demo data |
| Peer ratios | Peer list from Finnhub, ratios from Yahoo Finance | Demo data |

Formulas are in `core/ratios.py`, `core/valuation.py` and `core/quality_scores.py`, each with unit tests in `tests/test_ratios.py`. A few rules worth knowing:
- **No look-ahead in valuation history:** each day uses only the financial results that had been filed with the SEC by that day.
- **Stock splits:** EPS and share counts filed before a split are adjusted. Without this, NVDA's 2024 10-for-1 split would make its old P/E look 10× too high.
- **Negative earnings:** P/E shows "N/A (negative earnings)", never a negative number.
- **Banks and insurers:** EV/EBITDA, ROIC, the Altman Z-score, the DCF and similar items show N/A with the reason.

### Price, technicals and risk (Price & Technicals tab)

| What | Inputs | License |
|---|---|---|
| Candles, moving averages, RSI, MACD, Bollinger Bands, ATR, volume, support/resistance, pivots, signals | Daily prices from the price provider (yfinance now) | Demo data (becomes "Calculated" with the Nanovest price feed) |
| Returns, beta, volatility, drawdown, Sharpe, monthly returns | Dividend-adjusted prices of the stock, SPY, the sector ETF (`config/sector_etfs.yaml`) and `^IRX` | Demo data |
| Earnings markers on the chart | yfinance earnings dates (beat / miss %) | Demo data |

The formulas are in `core/technicals.py` and `core/risk.py`, with tests on synthetic prices in `tests/test_technicals.py`. Notes:
- **RSI and ATR** use Wilder's smoothing, the method most charting tools use, so values match them.
- **Support and resistance** levels are built in four steps:
  - Find swing highs and lows (5 days on each side) over 6 months, 1 year or 2 years.
  - Add the window's highest high and lowest low, so a brand-new 52-week high counts even before it's confirmed.
  - Group prices within max(0.5 × ATR, 1.5% of price) into one level. A group never stretches wider than that tolerance.
  - Rank levels by touches, with recent and high-volume touches counting more. The 3 strongest above and below the price are kept.
- **Trend signals** are facts with dates ("price is above its 200-day average"), never advice.

### Earnings (Earnings tab)

| What | Source (priority) | License |
|---|---|---|
| EPS estimate, reported EPS (usually adjusted), surprise %, report date and time | yfinance, then Finnhub | Demo data |
| GAAP diluted EPS, actual revenue, fiscal quarter labels | SEC EDGAR | Licensed-safe |
| Revenue estimates | Finnhub (free tier: latest quarter only) | Demo data |
| Estimate trend (90/60/30/7 days ago, now), up/down revisions, next-quarter estimates | yfinance | Demo data |
| 10-Q / 10-K and 8-K press release links | SEC EDGAR (8-K item 2.02 = results of operations) | Licensed-safe |

Rules (in `core/earnings.py`, tests in `tests/test_earnings.py`):
- **Beat / miss / inline:** beat if the surprise is above +1%, miss if below −1%, otherwise inline.
- **Price reaction:**
  - If the company reports before the market opens, the move is measured from the previous day's close.
  - If it reports after the close (or the time is unknown), the move is measured from that day's close to the next trading day's close, and 5 days later.
- **Quarter labels:** each report is matched to the fiscal quarter that ended just before it. If the 10-Q isn't filed yet, the quarter is marked "(est.)".
- **Expected EPS** is shown with 3 decimals. Providers round the estimate to cents but calculate the surprise from the exact value, so $0.40 vs $0.40 can correctly be a −1.1% "miss".

### Dividends, ownership, sentiment, news

| What | Source (priority) | License |
|---|---|---|
| Dividend history, ex-dividend dates, yield | yfinance (split-adjusted) | Demo data |
| Payout ratio, FCF payout | Calculated from SEC dividends paid, net income and free cash flow | Calculated |
| Dividends declared per share (cross-check) | SEC EDGAR | Licensed-safe |
| Holders, top institutions, insider transactions, short interest, rating changes | yfinance | Demo data |
| Wall Street analysts' ratings by month | Finnhub, then yfinance | Demo data |
| News | Finnhub company news, then yfinance | Demo data |
| SEC filings feed (8-K, 10-Q, 10-K, Form 4, ...) | SEC EDGAR | Licensed-safe |

Rules (in `core/dividends.py` and `core/sentiment.py`, tests in `tests/test_dividends_sentiment.py`):
- **Pays a dividend** = last dividend within about 15 months. Otherwise the tab shows "This company does not pay a dividend".
- **Growth streak** = consecutive calendar years in which the highest *regular* payment went up. Payments above 1.5× the year's median count as special dividends and are ignored. This gives KO 63 years.
  - Yahoo's records from the 1960s–80s can be incomplete, so some very long streaks are undercounted (e.g. PG, JNJ).
- **Yield history** = last year of payments ÷ that day's price. "Last year of payments" means the last 4 payments for a quarterly payer, not a fixed 365-day window, which would spike when payment dates shift by a day.
- **Insider buys and sells** count only open-market purchases and sales. Stock awards, gifts and option exercises are listed but not counted.

### Scorecard and insights (Summary tab)

- **Categories:** Valuation, Growth, Profitability, Financial health, Earnings quality, Momentum, Dividend.
- **Scores:** each category is scored 0–100 from several metrics.
  - **Strong** = 70+, **Neutral** = 40–69, **Weak** = below 40.
  - This is *our description of the data*, never a buy/sell recommendation.
- **Tuning without coding:** every threshold and weight is in `config/scoring.yaml`. Example: `revenue_yoy: {rule: higher_better, range: [-0.05, 0.15]}` gives 0 points at −5% growth and 100 points at +15%.
- **Missing data:** a category is scored from the metrics that are available ("based on 3 of 5 metrics"). With fewer than 2, it shows "Not enough data".
  - Banks get no Financial health score, because capital ratios aren't in free data.
  - Companies without a dividend show "Not applicable" for Dividend.
- **Strengths and Risks:** generated by rules in `config/scoring.yaml`, with up to 5 each, ordered by priority. The sentences are in `config/insights_en.yaml` and `config/insights_id.yaml`.
- **Production-safe mode:** metrics that use demo data (price, estimates, peers) are dropped, so scores use licensed-safe data only.
- **No buy/sell wording:** a test (`tests/test_scorecard.py`) checks that our texts contain none, in either language. Third-party analyst ratings appear only on the Ownership and Summary tabs, labeled "Wall Street analysts' ratings… not our view".
- **Interface text** (tabs, sidebar, header, summary) is in `config/ui_en.yaml` and `config/ui_id.yaml`; tooltips are in `config/glossary_*.yaml`.

## Project layout

```
config/      settings.py (reads .env), glossary_en.yaml / glossary_id.yaml (tooltips)
core/        data layer, reusable by Nanovest's real app
  providers/ base.py (interfaces), sec_edgar.py, yfinance_provider.py,
             finnhub_provider.py, nanovest_price.py (stub), registry.py (source priority)
  models.py  every value carries source + license tag
  company.py builds the header + profile from all sources
  cache.py   disk cache (.cache folder) with per-ticker refresh
app/         Streamlit page and components
tests/       pytest tests
logs/app.log one line per data-source call, with timing and success or failure
```

## Plugging in Nanovest's price feed later

Fill in the TODOs in `core/providers/nanovest_price.py`, then set `PRICE_PROVIDER="nanovest"` in `.env`.
If the Nanovest feed fails, the app falls back to yfinance automatically.

## Known limitations

- The API, data coverage page and the final performance pass come in Phase 8.
- In Bahasa Indonesia, the detailed chart titles and table headers inside the deeper tabs are still in English. Everything a first-time user reads is translated: tabs, sidebar, header, scorecard, strengths/risks and every tooltip.
- In production-safe mode the Dividends, Ownership and News sections are hidden (demo sources). The SEC filings feed and SEC-based payout ratio remain.
- Past revenue estimates need a paid data provider; the free sources only cover the latest quarter.
- In production-safe mode the Earnings tab is hidden (estimates and surprises are demo data). GAAP EPS and revenue stay visible on the Financials tab.
- In production-safe mode the whole Price & Technicals tab is hidden, because every number on it comes from demo price data until the Nanovest feed is connected.
- Our ratios can differ from Yahoo's:
  - **Timing:** right after a company reports earnings, Yahoo may already include the new quarter before the official SEC filing is out (for example NVDA in November 2026).
  - **Definitions:** Yahoo counts leases as debt and uses a different ROA formula.
  - A "Data check" panel at the bottom of the Valuation tab shows these differences.
- Peer ratios come from Yahoo while this stock's own row uses our SEC-based calculation, so the two methods can differ slightly.
- Stock split dates come from yfinance.
- "Revenue bars + net margin line" is drawn as two stacked panels on the same time axis, not one chart with two y-axes. Two y-axes on one chart can suggest a link between the lines that isn't there.
- MSFT and TSLA now report only plain depreciation (no amortization), so their EBITDA is slightly understated.
- For some companies SEC and yfinance define revenue differently (e.g. JPM, BRK). The data quality check shows these differences; SEC is the official number.
- The first time the Financials tab opens for a ticker it takes about 5–10 seconds to build the statements. After that it is cached for 24 hours.
- The language toggle currently switches tooltips, metric labels and the disclaimer. All other text follows in Phase 7.
- Peer fallback uses Yahoo industry groups. "Same SEC SIC code" peers need a bulk SEC index (planned).
- Berkshire Hathaway (and other multi-class companies) report shares per class, which the free SEC API does not split out, so their market cap uses Yahoo's number.
- yfinance is unofficial and can sometimes fail or rate-limit. The app then shows "N/A" with a reason.
- `pydantic` is pinned to 2.12.5 because Windows Application Control blocked the newer version's compiled file on this PC.
