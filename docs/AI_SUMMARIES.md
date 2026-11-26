# AI Insight summaries: how they work and what they cost

Each tab (Streamlit) and section (mobile prototype) can show an **AI Insight** card: a short, plain-language
explanation of the data on that page. Our code calculates every number; the AI only explains them. It is not advice.

## How a card is made

1. The input builder (`core/ai_summary/input_builder.py`) packs the tab's data into a small JSON object:
   numbers rounded, ratios as %, money in short units.
2. Claude (`claude-opus-5-5`, effort `medium`, prompt version 2.0) writes a structured answer (SPEC Section 16):
   - **bullish:** 0–4 points that support a positive view;
   - **bearish:** 0–4 points that support a negative view, or are risks;
   - **data_gaps:** 0–3 notes.

   Each point is a 2–6 word title plus one sentence of at most 25 words.
3. The validator checks it for banned buy/sell words, numbers that aren't in the data, and length limits. If a check
   fails, it retries once with a note. If it fails again, the card shows the rule-based **Automatic summary**:
   Section 7 strengths as bullish points and risks as bearish points.
4. The result is cached for 24 hours, or until the data changes.
5. Every attempt is logged to `logs/ai_summaries.jsonl`.
6. Thumbs up/down votes are saved to `logs/ai_feedback.jsonl`.

Turning the cards off: set `AI_SUMMARIES_ENABLED=false`, or leave `ANTHROPIC_API_KEY` empty. Every card disappears
and nothing else changes.

## Expected cost (measured in step 10b, 100 summaries, November 2026)

Prices for claude-opus-5-5: $4 per million input tokens, $20 per million output tokens, cache reads $0.20 per million.

| Tab | Average cost per summary |
|---|---|
| Financials (biggest input) | $0.096 |
| Summary, Valuation, Earnings, Price & Technicals | about $0.06–0.07 |
| Profitability & Health, Ownership, News, Profile | about $0.05–0.06 |
| Dividends (smallest) | $0.032 |
| **Average** | **$0.062** |

| Per stock | Cost |
|---|---|
| All 10 tabs, one language | about $0.62 |
| All 10 tabs, English + Indonesian | about **$1.25** (measured: AAPL $1.41, KO $1.36, TSLA $1.27, JPM $1.01, PLUG $1.19) |

- About 35% of that is retries after a failed check. Planned validator and prompt fixes (see the 10b report) should
  bring it to about $0.85 per stock.
- A cached card costs nothing. One stock costs the amounts above once per day, however many people open it.
- A first-time card takes about 26 seconds on average (up to about 1 minute), so the UI shows a skeleton loader.

## Note for production

- **Pre-generate, don't generate per user.** Once a day, generate summaries for popular tickers with the
  [Batch API](https://docs.claude.com/en/docs/build-with-claude/batch-processing), which costs half as much, and
  serve them from the cache. Cost then grows with the number of tickers, not the number of users.
  - Example: 500 tickers × 20 summaries × $0.062 × 50% batch discount ≈ **$310 per day**. For the top 100 tickers,
    about $62 per day.
- Generate other tickers only when someone opens them, as the prototype does now. Tabs are generated one at a time,
  never all at once.
- Watch `logs/ai_feedback.jsonl` (thumbs down) and the share of automatic-summary fallbacks in
  `logs/ai_summaries.jsonl`.
- The data behind many cards is DEMO_ONLY (yfinance/Finnhub). A licensed data provider is needed before any public
  launch.
