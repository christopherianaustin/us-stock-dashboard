# UI analysis: Nanovest US stock asset page (Phase 9a)

Step 9a of SPEC Section 14: analyse the current design before any app code is written.
**Status: decisions confirmed on 25 Nov 2026 (section 0). A few small questions remain (section 9), each with the default I'll use if you don't answer.**

## 0. Confirmed decisions

| # | Topic | Decision | What it means in the prototype |
|---|---|---|---|
| 1 | Currency | **Rupiah (Rp)** for every money amount | US dollar values from the API are converted to Rp with a USD/IDR rate (section 4.2). Ratios and percentages are not converted. |
| 2 | Number format | **Comma for thousands, dot for decimals**, e.g. `Rp 5,762,315` and `1.02%` | Same format in English and Bahasa Indonesia. |
| 3 | Font | **Free substitute for Gilroy: Plus Jakarta Sans** (Google Fonts, free license) | Gilroy Medium → Plus Jakarta Sans 500; Gilroy Bold → 700. Same sizes and line heights as the Figma text styles (section 4). |
| 4 | Theme | **Light only** | No dark mode. |
| 5 | Layout | **Pill tabs on the stock page:** Analysis · Fundamentals · News · Financials · Technicals · About. Each tab has its own content. **Key stats as horizontal cards.** | This replaces the separate "Full analysis" page from the first draft. The full layout is in section 8. |

## 1. Inputs used

| Input | Status |
|---|---|
| Figma frame `104-Stock Portfolio` (file `Stocks`, node `1015:98420`), read with the Figma MCP. No other pages were opened. | ✅ Used |
| PNG of the frame | ✅ Saved as `design/nanovest-screens/01-us-stock-asset-page.png` (375 × 2964, 1×) |
| Figma variables (colors, text styles, shadow) bound to this frame | ✅ Used; treated as the design tokens |
| Design context for 3 parts (top info, Key Stats card, Analyst ratings card) | ✅ Used for exact sizes, fonts and spacing |
| `design/design-tokens.md`, `design/notes.md`, `design/assets/` | ❌ Not provided. Behaviour of taps / bottom sheets is therefore guessed (listed in section 9). |
| Dark-mode screens, bottom sheets, "View all" pages, tab screens | ❌ Not in this frame |

The frame is **375 px wide** (iPhone 8/X-class artboard). The spec asks for a 390 × 844 phone frame; see section 9, Q11.

## 2. The current page, top to bottom

| # | Section (Figma layer) | What it shows | y (px) |
|---|---|---|---|
| 1 | Status bar + **Small header** | Back arrow (left); heart, bell, share icons (right) | 0–102 |
| 2 | **Top Info** | Round logo avatar (48 px, dark navy) + ticker `AAPL`; company name `Apple`; price `$200`, red ↙ change `1.02%`, ⓘ | 102–222 |
| 3 | **Graphic** | Line chart, full bleed (no axes, no grid), time chips `1D 1W 1M 1Y All` | 238–534 |
| 4 | **Buy / Sell** | Two dark pill buttons, 156 × 48 each | 556–604 |
| 5 | Divider | 8 px full-width band, `#F4F7F9` | 628 |
| 6 | **My Holding** card | Portfolio value `$ 735.10`, rows: Shares, Avg. Cost, Total Return, Total Return % (each with a small purple icon) | 660–966 |
| 7 | **Company details** card (`Apple Inc. \| AAPL`) | 4-line description + "Read more", rows: CEO, Industry, Number of Employee | 990–1304 |
| 8 | **Key Stats** card | Rows: Share price, Market cap, P/E Ratio | 1328–1514 |
| 9 | **Analyst ratings** card (ⓘ) | 1–5 slider with value bubble (`1.2`), "Based on 123 reviews", 5 percentage bars (Strong buy … Strong Sell) | 1538–1966 |
| 10 | **Price Target Forecast** card (ⓘ) | Text, "Updated on Mar 14, 2022", `Rp` / `%` chips, chart with Current → High / Target / Low callouts on green / red zones | 1990–2448 |
| 11 | Divider | 8 px band | 2472 |
| 12 | **News** | Title + "See the latest news on this stock!" + purple "View all"; horizontally scrolling news cards (source avatar, 4-line headline, "1s ago") | 2480–2764 |
| 13 | **Featured in** | Two rows of outlined pill chips (All Stocks, Top 100, Sports, …), horizontally scrolling | 2764–2926 |
| 14 | Home indicator | | 2930 |

Hidden layers in the frame (exist but switched off): a **2-tab bar** at the top of the content area, a **"Safe" badge** next to the ticker, an **Rp price variant** (`Rp. 3.100`), a **Bank selection** row and a **"Compro" small menu button**. Their meaning is unknown (section 9).

## 3. Colors

From the Figma variables, so these are exact:

| Token (Figma name) | Hex | Used for |
|---|---|---|
| Primary/Black | `#082F57` | Main text: card titles, row labels and values, price |
| Primary/Black Background (dark) | `#111A28` | Buy / Sell buttons, logo avatar background, chart line |
| Primary/White | `#FFFFFF` | Page and card background |
| Brand/Purple | `#561FA3` | Accent: "Read more", "View all", chevrons, slider, rating bars, selected `Rp` chip, holding-row icons |
| Shade Avatar/Purple | `#F7F3FF` | Round background behind the chevron button |
| Shade/Dark Grey | `#7C8D9D` | Secondary text: company name, ticker, "Based on 123 reviews", news time |
| Shade/Grey | `#A3B1BE` | Inactive text: unselected time chips, minor rating labels |
| Shade/Grey-2 | `#E8EBEF` | Bar tracks, ⓘ circle, selected time-chip background |
| Shade/Light Grey | `#F4F7F9` | 8 px section dividers |
| Product/Green | `#06CB90` | Price up, "High" forecast callout |
| Shade Avatar/Green | `#E6FAF4` | Background behind green (up) icons |
| Product/Red | `#E11C23` | Price down (`1.02%`), "Low" forecast callout |
| Shade Avatar/Red | `#FCE8E9` | Background behind the red (down) arrow |
| Shade Avatar/Black | `#E6EAEE` | Neutral avatar background |
| Label Color/Light/Primary | `#000000` | iOS status bar only |

Seen in the image but not tokenized, so these are approximate:
- **Forecast chart zones:** very light green (≈ `#E6FAF4`) above the current price and very light red (≈ `#FCE8E9`) below. The card bottom has a soft lavender-to-blue tint.
- **"Current" callout:** purple-to-blue gradient (≈ `#9C7CF5` → `#5BA8F5`). "Target" callout = Brand/Purple.
- **Analyst slider track:** green → dark → red gradient.

## 4. Typography

**One typeface: Gilroy** (Bold 700 and Medium 500; no other weights seen, no italics).

| Style (Figma name) | Font | Size / line height | Used for |
|---|---|---|---|
| Title | Gilroy Bold | 24 / 32 | Company name ("Apple"), in Dark Grey |
| Sub Title | Gilroy Bold | 18 / 28 | Price `$200`, change `1.02%`, section titles "News", "Featured in" (estimated) |
| Text Link | Gilroy Bold | 16 / 26 | Card titles, row values, ticker, "Read more" (purple) |
| *(Body, not tokenized)* | Gilroy Medium | 16 / 26 | Row labels, descriptions, "Based on…" |
| Label | Gilroy Bold | 14 / 20 | Rating bar labels ("89 % Strong buy") |
| Action | Gilroy Medium | 12 / 16 | Slider axis labels, "Updated on…" |
| Action Bold | Gilroy Bold | 12 / 16 | Slider value bubble, chip text |

Other type notes:
- Letter spacing is always 0.
- Numbers use the default (proportional) digits.
- Headline hierarchy comes from weight and color (navy vs grey), not from large size jumps.

### 4.1 Font used in the prototype (confirmed)

**Plus Jakarta Sans**, loaded from Google Fonts. It's free (SIL Open Font License) and replaces Gilroy, which is a paid font.

| Figma style | Gilroy | Prototype |
|---|---|---|
| Title | Bold 24 / 32 | Plus Jakarta Sans 700, 24 / 32 |
| Sub Title | Bold 18 / 28 | Plus Jakarta Sans 700, 18 / 28 |
| Text Link | Bold 16 / 26 | Plus Jakarta Sans 700, 16 / 26 |
| Body | Medium 16 / 26 | Plus Jakarta Sans 500, 16 / 26 |
| Label | Bold 14 / 20 | Plus Jakarta Sans 700, 14 / 20 |
| Action | Medium 12 / 16 | Plus Jakarta Sans 500, 12 / 16 |
| Action Bold | Bold 12 / 16 | Plus Jakarta Sans 700, 12 / 16 |

Why this font, and what to watch for:
- Like Gilroy, it's a geometric sans with round letters and a tall x-height.
- It was made by an Indonesian type foundry (Tokotype).
- It runs a little wider than Gilroy, so long values in rows are checked for overflow at 390 px in step 9b.
- If Nanovest's real Gilroy files are added to `design/assets/` later, only one line in the font setup changes.

### 4.2 Currency and number format (confirmed)

- **Currency: Rupiah.** Every money amount from the API (price, market cap, EPS, revenue, dividends per share, price targets, fair value…) is shown in Rp.
- **Conversion:** amount in USD × USD/IDR rate.
  - The rate comes from Yahoo Finance (`IDR=X`, demo data) through the API.
  - If that fails, a fixed rate from the prototype config is used, labeled **"Mock rate"**.
  - The rate and its date are shown in small grey text under the price, e.g. "1 USD = Rp 16,xxx · 25 Nov 2026".
- **Not converted:** ratios (P/E, ROE, beta…), percentages and share counts.
- **Number format:** comma for thousands, dot for decimals, in both languages.
- **Decimal places:**

| What | Example |
|---|---|
| Rp amounts | no decimals: `Rp 5,762,315` |
| Percentages | 2 decimals: `1.02%`, `-18.03%` |
| Ratios | 2 decimals: `38.93` (P/E shown as `38.93x` in the stat cards) |
| Share counts | whole numbers: `143,943,123` |

- **Big amounts use short words**, following the Figma forecast axis ("Rp 20 M"):
  - English: K (thousand), M (million), B (billion), T (trillion). Example: Apple's market cap ≈ `Rp 84,000 T`.
  - Bahasa Indonesia: Rb, Jt, M (miliar), T (triliun).
- **The Price Target Forecast card keeps its Rp / % switch:** Rp shows the targets in Rupiah; % shows them as change from today's price.

## 5. Spacing, radius, shadow

**Spacing**
- **Page side padding:** 24 px, so a card is 327 px wide on a 375 px screen.
- **Card inner padding:** 16 px.
- **Card title row:** 28 px high, with the first content line at 60 px from the card top.
- **Rows ("2 Detail list"):** 26 px high, starting every 42 px (16 px gap). Label left in Medium, value right in Bold.
- **Gap between cards:** 24 px.
- **Section dividers:** 8 px full-width bands in Light Grey, between big page zones (after the buttons, before News).
- **Buttons:** 2 × 156 × 48 with a 15 px gap.
- **Time chips:** 26 px high, centered under the chart.

**Corner radius**
- Cards: 16
- Chevron button: 28 px circle (radius 20)
- Logo avatar: full circle
- Buy / Sell buttons, time chips, "Featured in" chips, `Rp` / `%` chips: full pill
- Rating bars: 8
- Slider value bubble: 4
- News cards: ≈ 16

**Shadow**
- Only one shadow is used, "Drop Shadow" `0 7px 25px rgba(33,33,33,0.10)`, on every card.
- Dividers carry the rest of the hierarchy.

## 6. Icons

**Nav bar:** solid navy (`#082F57`) icons at 24 px: back arrow, filled heart, filled bell, share.

**Status and info icons**
- **Price change:** 16 px diagonal arrow (↙ down / ↗ up) in red or green, on a circle tinted the matching shade (`#FCE8E9` / `#E6FAF4`).
- **Info:** a small "i" in a grey (`#E8EBEF`) circle. 16 px in the price row, 24 px in card titles.
- **Collapse / expand:** purple `chevron-up` 24 px inside a 28 px lavender (`#F7F3FF`) circle. "Up" means the card is open.

**Content icons**
- **Holding rows:** small purple glyphs (#, Rp, ↗, %) on white circles with a soft shadow.
- **My Holding:** a 48 px purple rounded-square icon with a bar-chart glyph.
- **News:** each card has a round source logo.

**Icon library:** looks custom (Nanovest's own set). The SVGs can be exported from Figma for step 9b.

## 7. Components

| Component | Description | Reuse for new features |
|---|---|---|
| **Small header** | Back + 3 action icons | Same; also on the "See full statement" page |
| **Top info** | Avatar, ticker, name, price + change chip + ⓘ | Add the **next earnings chip** under the price row |
| **Line chart + time chips** | Clean line, no axes; pill chips, selected = grey fill | Keep at the top as is; the Technicals tab gets its own chart with candles and a support/resistance toggle |
| **Primary button** | Dark pill, white Bold 16 text | Buy / Sell: visual only ("Prototype only") |
| **Collapsible card** | White, radius 16, shadow, title row + chevron | **Main building block** for every new section |
| **2 Detail list row** | Label (Medium) left, value (Bold) right | Ratio lists and statement summaries |
| **Read more** link | Inline purple Bold | Long explanations |
| **Slider with value bubble** | 1–5 scale | Existing Wall Street analyst rating: keep as is |
| **Percentage bars** | 8 px track, purple fill, label right | Beat rate, rating counts, Piotroski checks |
| **Rp / % chip toggle** | Selected purple, unselected outlined | **Quarterly / Annual** and range switches (pattern reused) |
| **Forecast chart with callouts** | Zones + colored callout labels | Fair value estimate (Graham / DCF / analyst targets) |
| **Horizontal carousel** | News cards, peek of next card | **Key stats cards** (as the spec asks) |
| **Outlined chip cloud** | "Featured in" | Peers / similar companies |
| **Divider band** | 8 px Light Grey | Separates page zones |
| **ⓘ icon** | No tooltip shown in Figma | Opens a **bottom sheet** with the glossary text (new, styled like a card) |

## 8. Page layout with pill tabs (confirmed direction)

The stock asset page keeps its top part exactly as in Figma. Below it sits a row of **pill tabs**. Each tab shows its own content, built from the existing card style:
- White, 16px corners, soft shadow.
- Title row with a chevron to collapse or open the card.
- Label/value rows.

The existing cards (Company details, Key Stats, Analyst ratings, Price Target Forecast, News, Featured in) move into the tab where they fit best, so nothing from the current page is lost.

### 8.1 The page

```
┌───────────────────────────────┐
│ ←                    ♥  🔔  ⤴ │  Small header (unchanged)
│ (logo) AAPL                   │
│ Apple                         │
│ Rp 5,762,315  ↙1.02%  ⓘ       │  price in Rp (Sub Title, navy)
│ 1 USD = Rp 16,xxx · 25 Nov    │  NEW: exchange rate (Action, grey)
│ [Earnings 28 Jan · in 64 days]│  NEW: next earnings chip (grey pill)
│ ~~~~~~~~ line chart ~~~~~~~~  │  (unchanged)
│    1D  1W  1M  1Y  All        │
│ [   Buy   ]   [   Sell   ]    │  visual only: tap → "Prototype only"
│▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒│  divider
│ ┌ My Holding ─────────── ⌃ ┐  │  (unchanged)
│ └──────────────────────────┘  │
│ (Analysis)(Fundamentals)(News)(Financials)(Technicals)(About) ▶
│                               │  NEW: pill tabs, scroll sideways,
│                               │  stick under the header when scrolling
│ ┌ content of the selected ──┐ │
│ │ tab (cards, see 8.3)      │ │
│ └───────────────────────────┘ │
│ Disclaimer (Action, grey)     │  under every tab
└───────────────────────────────┘
```

### 8.2 Pill tab style

- **Shape:** each pill is 36 px high, with 16 px space on each side and fully rounded ends. There's 8 px between pills, and the row scrolls sideways with a 24 px page margin.
- **Selected pill:** Brand/Purple `#561FA3` fill with white text in Label style (14/20 bold). This is the same look as the selected `Rp` chip in the Figma frame.
- **Unselected pill:** white with a 1 px `#E8EBEF` border and Dark Grey `#7C8D9D` text.
- **Default tab:** Analysis.
- **Switching tabs:** the content cross-fades. The page doesn't jump back to the top unless the tab row is out of view.
- **Language:** labels switch with the EN / ID setting: Analysis / *Analisis*, Fundamentals / *Fundamental*, News / *Berita*, Financials / *Keuangan*, Technicals / *Teknikal*, About / *Tentang*.

### 8.3 What each tab contains

Cards are listed top to bottom. The first one or two cards in each tab start open and the rest start collapsed, so the phone screen stays short. Every ⓘ opens a **bottom sheet**: white, rounded top corners, grab handle, with the glossary text in EN / ID ("What it means", "How it's calculated", "Good or bad?").

**Tab 1: Analysis** (default)

| Card | Content | Data from |
|---|---|---|
| Stock analysis ⓘ | **7 category pills** (Valuation, Growth, Profitability, Financial health, Earnings quality, Momentum, Dividend), each Strong / Neutral / Weak. **What looks good**: top 3 strengths. **What to watch**: top 3 risks. Note: "Our read of the data, not advice." | `/summary` |
| Key stats | **Horizontal cards** you scroll sideways: P/E, P/S, EV/EBITDA, Revenue growth (YoY), Net margin, ROE, Debt to equity, Dividend yield, Beta. Each card shows the value, a plain label (e.g. "Pricier than usual", "Low debt") and ⓘ. **Tapping a card opens a bottom sheet** with the explanation and one everyday sentence. | `/summary`, `/ratios` |
| Analyst ratings ⓘ | Existing card, unchanged design, plus a small label: "Wall Street analysts' ratings, not Nanovest's view". | `/ownership` |
| Price Target Forecast ⓘ | Existing card, with the Rp / % switch and real low / mean / high targets. | `/valuation` |
| How we scored this (collapsed) | Radar of the 7 categories, plus each category's score and "based on X of Y metrics". | `/summary` |

**Tab 2: Fundamentals**

| Card | Content | Data from |
|---|---|---|
| Valuation | Rows: Share price (Rp), Market cap (Rp), P/E, P/S, P/B, EV/EBITDA, FCF yield, each with "vs its 5-year median" and "vs peers". P/E over 5 years: a line with a median line and band. Sentence: "P/E is higher than 93% of the last 5 years." | `/valuation`, `/ratios` |
| Fair value estimate ⓘ | Forecast-style chart with callouts: today's price vs Graham number, DCF (bear / base / bull) and analysts' mean target, all in Rp. Big label: "Estimate based on assumptions. Not a prediction." | `/valuation` |
| Profitability | ROE, ROA, ROIC, gross / operating / net margin (TTM), with a plain label each. ROE breakdown in 3 rows: margin × turnover × leverage. | `/ratios` |
| Growth | Revenue and EPS growth vs last year; 3- and 5-year growth per year (CAGR). | `/ratios` |
| Financial health ⓘ | Piotroski checklist: 9 rows with ✓ / ✗ and a short explanation, score x / 9. Altman Z-score as a bar with Safe / Grey / Distress zones (hidden with a reason for banks). Debt & cash rows: net debt (Rp), debt to equity, current ratio, interest coverage. | `/ratios` |
| Dividends | If the company pays one: yield, payout ratio, years of raises, next ex-dividend date, dividend per share by year (bars, Rp). If not: "This company does not pay a dividend." | `/dividends` |

**Tab 3: News**

| Card | Content | Data from |
|---|---|---|
| Latest news | `7 days` / `30 days` pill switch. Vertical list in the existing news-card style: source logo, source name, headline (3 lines), time ago. Tap opens the article. | `/news` |
| SEC filings | Rows: form (10-K, 10-Q, 8-K, Form 4), date, short description ("Earnings results"). Tap opens the filing on the SEC website. | `/news` |

**Tab 4: Financials**

| Card | Content | Data from |
|---|---|---|
| Period switch | `Quarterly` / `Annual` pills at the top of the tab; they apply to every card below. | — |
| Revenue & profit | Bars for revenue and net income (last 8 quarters or 5 years, Rp, short labels like "Q4 FY26"), plus the net margin. Tap a bar to see exact values. | `/financials` |
| Margins | Lines for gross, operating and net margin. | `/financials` |
| Cash flow | Bars for operating cash flow, capex and free cash flow (Rp). | `/financials` |
| Cash vs debt | Bars for cash vs total debt, plus the net debt value (Rp). | `/financials` |
| Earnings | Next earnings (date, time, expected EPS and revenue in Rp, analysts covering). EPS actual vs expected bars (8 quarters, green = beat, red = miss). Beat rate (last 8 quarters) and typical price move after earnings. | `/earnings` |
| See full statement › | Opens a full-screen page with `Income` / `Balance` / `Cash flow` pills and a sideways-scrolling table (Rp, derived values marked). | `/financials` |

**Tab 5: Technicals**

| Card | Content | Data from |
|---|---|---|
| Price chart | TradingView Lightweight Charts (with attribution). Line / candle switch; ranges `1M 3M 6M 1Y 3Y 5Y`; toggles for moving averages and support / resistance. Tap to see the exact price (Rp). | `/technicals` |
| Support & resistance ⓘ | Rows: level (Rp), distance from today's price, strength. Note: "Areas where price reacted before. Not guarantees." | `/technicals` |
| Momentum | RSI with the 30 / 70 zones, MACD (bars), and a signals list of facts with dates ("Price is above its 200-day average", "MACD crossed below its signal line · 19 Nov"). | `/technicals` |
| Performance vs S&P 500 | Return rows for 1M / 3M / 6M / YTD / 1Y / 3Y / 5Y: stock vs S&P 500 vs sector, plus a small line chart starting at 100. | `/technicals` |
| Risk | Beta, volatility (1 year), biggest drop (1 year and 5 years), Sharpe ratio, each with a plain label. | `/technicals` |

**Tab 6: About**

| Card | Content | Data from |
|---|---|---|
| Company details | Existing card: description + "Read more", rows CEO, Industry, Number of employees, plus Sector, Headquarters, Website, Exchange, Fiscal year end, IPO date. | `/profile` |
| Ownership | Insiders % / institutions % (donut), top 5 institutional holders, insider buying / selling per month, short interest. | `/ownership` |
| Similar companies | Peers as outlined chips (existing "Featured in" style). Tap one to open that stock's page. | `/profile` |
| Featured in | Existing chips, unchanged. | mock (no data source) |

**Hidden debug menu.** Tap the ticker text 5 times to open it. It holds:
- "Data badges": shows the green / blue / orange source badges.
- "Mock data mode": on or off.
- An EN / ID switch.

Fields hidden by PRODUCTION_SAFE_MODE show "Requires licensed data provider".

### 8.4 States (every tab)

- **Loading:** skeleton blocks in the card shapes, in Grey-2 `#E8EBEF`.
- **Missing data:** grey text "N/A · reason" (e.g. "N/A · Banks don't report gross profit").
- **Error:** a single line in the card, "Couldn't load this section. Tap to retry." The other tabs keep working.
- **No dividend / no news:** a short friendly message in place of the card content.

## 9. Remaining questions (with the default I'll use)

These are small. If you don't answer, I'll go ahead with the default.

| # | Question | Default |
|---|---|---|
| 1 | The existing **Analyst ratings** card says "Strong buy / Buy / Sell". Add the label "Wall Street analysts' ratings, not Nanovest's view"? | Yes, add the label |
| 2 | Copy typos in Figma ("What analyst rate…", "arround", "Number of Employee"): keep or fix? | Fix them |
| 3 | Hidden layers in the frame ("Safe" badge, 2-tab bar, Bank selection, Compro): show any of them? | Keep them hidden |
| 4 | The frame is 375 px; the prototype is 390 × 844. Keep 24 px side padding and let cards stretch to 342 px? | Yes |
| 5 | Logos for other tickers: Finnhub logo (demo data), with initials in a navy circle as fallback? | Yes |
| 6 | The main chart at the top stays a simple line (as in Figma); candles only in the Technicals tab? | Yes |
| 7 | **My Holding**: there's no portfolio data. Show it with example numbers labeled "Example holding", or hide it? | Show, labeled "Example holding" |
| 8 | The News and Featured in sections at the bottom of the current page move into the News and About tabs, so they don't appear twice. OK? | Yes, move them |
| 9 | USD/IDR rate: from Yahoo Finance (demo), with a fixed fallback rate labeled "Mock rate". OK? | Yes |
