// Time to first screen (name + price + price chart drawn) for each ticker: a first visit, then a repeat visit
// in the same browser (like a real phone, so the repeat visit can use the browser copy).
// Usage: node scripts/perf.mjs [mode=auto] [tickers...]   (needs `npm run preview`, and the API for live/auto)
import { chromium } from 'playwright'

const [mode = 'auto', ...rest] = process.argv.slice(2)
const tickers = rest.length ? rest : ['AAPL', 'KO', 'TSLA', 'JPM', 'BRK-B']
const browser = await chromium.launch({ channel: 'chrome', headless: true })
const out = {}
for (const t of tickers) {
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 } })
  const times = []
  for (let run = 0; run < 2; run++) {
    const page = await ctx.newPage()
    const t0 = Date.now()
    await page.goto(`http://127.0.0.1:4173/?t=${t}&mode=${mode}`, { waitUntil: 'domcontentloaded' })
    await page.locator('h1').waitFor({ timeout: 120000 })
    await page.locator('canvas').first().waitFor({ timeout: 120000 }).catch(() => {})
    times.push(Date.now() - t0)
    await page.close()
  }
  await ctx.close()
  out[t] = { firstVisitMs: times[0], repeatVisitMs: times[1] }
}
console.log(JSON.stringify(out, null, 1))
await browser.close()
