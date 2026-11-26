// Step 10c check: every section with an AI Insight shows it, in English and Indonesian.
// Default: saved data (mode=mock, no API cost). Screenshots go to design/final/ai_*.png.
// Needs `npm run preview` (127.0.0.1:4173).   Usage: node scripts/check-ai.mjs [TICKER=AAPL] [mode=mock]
import { existsSync, mkdirSync, readFileSync } from 'node:fs'
import { chromium } from 'playwright'

const T = process.argv[2] ?? 'AAPL'
const MODE = process.argv[3] ?? 'mock'
const OUT = '../design/final'
mkdirSync(OUT, { recursive: true })
const TABS = {   // AI sections on each pill tab
  analysis: ['summary'], fundamentals: ['valuation', 'profitability_health', 'dividends'], news: ['news_filings'],
  financials: ['financials', 'earnings'], technicals: ['price_technicals'], about: ['company_profile', 'ownership_sentiment'],
}
/** With saved data we know the answer: an automatic summary with no points is hidden on purpose. */
function expected(lang, tabs) {
  if (MODE !== 'mock') return tabs.length
  return tabs.filter((a) => {
    const f = `public/mock/${T}/ai_${a}_${lang}.json`
    if (!existsSync(f)) return false
    const d = JSON.parse(readFileSync(f, 'utf8')).data
    return d.source === 'ai' || d.summary.bullish.length + d.summary.bearish.length > 0
  }).length
}
const browser = await chromium.launch({ channel: 'chrome', headless: true })
let bad = 0

for (const lang of ['en', 'id']) {
  for (const [tab, list] of Object.entries(TABS)) {
    const want = expected(lang, list)
    const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2 })
    const page = await ctx.newPage()
    const errs = []
    page.on('pageerror', (e) => errs.push(e.message))
    await page.goto(`http://127.0.0.1:4173/?t=${T}&lang=${lang}&mode=${MODE}&tab=${tab}&statusbar=1`)
    await page.waitForTimeout(1500)
    for (let i = 0; i < 12 && await page.locator('[data-toggle="closed"]').count(); i++) await page.locator('[data-toggle="closed"]').first().click()
    // scroll through so every block comes into view and loads
    const h = await page.evaluate(() => document.documentElement.scrollHeight)
    await page.setViewportSize({ width: 390, height: h })
    await page.waitForFunction(() => ![...document.querySelectorAll('[data-ai-insight] [data-skeleton]')].length, null, { timeout: 150000 }).catch(() => {})
    await page.waitForTimeout(800)
    const n = await page.locator('[data-ai-insight]').count()
    const heads = await page.locator('[data-ai-insight] li b').allInnerTexts()
    const sides = await page.locator('[data-ai-insight] [data-ai-side]').count()
    const ok = n === want && sides === 2 * n && !errs.length
    if (!ok) bad++
    console.log(`${ok ? 'OK ' : 'BAD'} ${T} ${lang} ${tab}: ${n}/${want} AI blocks, ${sides} bullish/bearish lists ${errs.length ? 'errors: ' + errs.join(' | ') : ''}`)
    heads.forEach((x) => console.log('     ' + x))
    if (tab === 'analysis' || tab === 'fundamentals') await page.screenshot({ path: `${OUT}/ai_${T}_${tab}_${lang}.png` })
    await ctx.close()
  }
}
// "Show all" and feedback on the first block
{
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2 })
  const page = await ctx.newPage()
  await page.goto(`http://127.0.0.1:4173/?t=${T}&lang=en&mode=${MODE}&statusbar=1`)
  const box = page.locator('[data-ai-insight]').first()
  await box.scrollIntoViewIfNeeded()
  const showAll = box.getByRole('button', { name: 'Show all' })
  if (await showAll.count()) await showAll.click()
  await box.getByRole('button', { name: 'Helpful', exact: true }).click()
  await page.waitForTimeout(400)
  console.log('Show all + feedback:', (await box.innerText()).includes('Thanks for the feedback') ? 'OK' : 'BAD')
  await box.screenshot({ path: `${OUT}/ai_${T}_card_more.png` })
  await ctx.close()
}
await browser.close()
console.log(bad ? `${bad} problem(s)` : 'All sections show the AI Insight.')
process.exit(bad ? 1 : 0)
