// Final presentation screenshots (Phase 9d) → design/final/
// Every tab in English and Indonesian, plus the loading, error, empty, offline and tap states.
// Needs `npm run preview` (127.0.0.1:4173) and the API (127.0.0.1:8000).
// Usage: node scripts/shoot-final.mjs [TICKER=AAPL]
import { mkdirSync } from 'node:fs'
import { chromium } from 'playwright'

const T = process.argv[2] ?? 'AAPL'
const OUT = '../design/final'
mkdirSync(OUT, { recursive: true })
const BASE = 'http://127.0.0.1:4173/?statusbar=1'
const TABS = ['analysis', 'fundamentals', 'news', 'financials', 'technicals', 'about']
const browser = await chromium.launch({ channel: 'chrome', headless: true })
const shots = []

async function newPage() {
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2 })
  const page = await ctx.newPage()
  return { ctx, page }
}
const settle = async (page) => {
  await page.waitForFunction(() => !document.querySelector('[data-skeleton]'), null, { timeout: 90000 }).catch(() => {})
  await page.waitForTimeout(600)
}
async function expandAll(page) {
  for (let i = 0; i < 12 && await page.locator('[data-toggle="closed"]').count(); i++) await page.locator('[data-toggle="closed"]').first().click()
  await settle(page)
}
/** Screenshot the whole page: make the window as tall as the page so every chart is drawn. */
async function full(page, name) {
  const h = await page.evaluate(() => document.documentElement.scrollHeight)
  await page.setViewportSize({ width: 390, height: h })
  await page.waitForTimeout(700)
  await page.screenshot({ path: `${OUT}/${name}.png` })
  await page.setViewportSize({ width: 390, height: 844 })
  shots.push(name)
}
async function screen(page, name) {
  await page.waitForTimeout(400)
  await page.screenshot({ path: `${OUT}/${name}.png` })
  shots.push(name)
}

// 1. Every tab, English and Indonesian
for (const lang of ['en', 'id']) {
  const { ctx, page } = await newPage()
  await page.goto(`${BASE}&t=${T}&lang=${lang}`)
  await page.locator('h1').waitFor({ timeout: 120000 })
  await settle(page)
  if (lang === 'en') await screen(page, `00-${T}-first-screen-en`)
  for (const [i, tab] of TABS.entries()) {
    await page.locator('[role="tab"]').nth(i).click()
    await settle(page)
    await expandAll(page)
    await page.evaluate(() => scrollTo(0, 0))
    await full(page, `${String(i + 1).padStart(2, '0')}-${T}-${tab}-${lang}`)
  }
  await ctx.close()
}

// 2. Tap interactions: explanation sheet, full statement, prototype settings
{
  const { ctx, page } = await newPage()
  await page.goto(`${BASE}&t=${T}`)
  await page.locator('h1').waitFor({ timeout: 120000 })
  await settle(page)
  await page.locator('section button[aria-label^="P/E"]').first().scrollIntoViewIfNeeded()
  await page.locator('section button[aria-label^="P/E"]').first().click()
  await screen(page, `20-${T}-tap-key-stat-sheet`)
  await page.getByRole('button', { name: 'OK' }).click()
  await page.waitForTimeout(300)
  await page.locator('[role="tab"]').nth(3).click()
  await settle(page)
  await page.getByText('See full statement').click()
  await settle(page)
  await screen(page, `21-${T}-full-statement`)
  await page.getByRole('dialog').getByLabel('Back').click()
  await page.evaluate(() => scrollTo(0, 0))
  for (let i = 0; i < 5; i++) await page.locator('h1').locator('xpath=preceding-sibling::div//button').click()
  await screen(page, `22-prototype-settings`)
  await ctx.close()
}

// 3. Loading state (API answers slowly)
{
  const { ctx, page } = await newPage()
  await page.route('**/127.0.0.1:8000/**', async (r) => { await new Promise((ok) => setTimeout(ok, 8000)); r.continue() })
  await page.goto(`${BASE}&t=${T}`)
  await page.waitForTimeout(3800) // after 3 s the "first load can take up to 20 seconds" note appears
  await screen(page, `30-loading`)
  await ctx.close()
}

// 4. Error states
{
  const { ctx, page } = await newPage()
  await page.goto(`${BASE}&t=ZZZZZ&mode=live`)
  await page.locator('[role="alert"]').waitFor({ timeout: 120000 })
  await screen(page, `31-error-unknown-ticker`)
  await ctx.close()
}
{
  const { ctx, page } = await newPage()
  await page.route('**/127.0.0.1:8000/**', (r) => r.abort('connectionrefused'))
  await page.goto(`${BASE}&t=MSFT`)
  await page.locator('[role="alert"]').waitFor({ timeout: 60000 })
  await screen(page, `32-error-api-off-no-saved-data`)
  await ctx.close()
}
{
  // one section fails, the rest of the page still works
  const { ctx, page } = await newPage()
  await page.route('**/ownership**', (r) => r.fulfill({ status: 503, contentType: 'application/json', body: '{"detail":"Upstream timeout"}' }))
  await page.goto(`${BASE}&t=${T}&mode=live`)
  await page.locator('h1').waitFor({ timeout: 120000 })
  await settle(page)
  await full(page, `33-error-one-section`)
  await ctx.close()
}

// 5. Offline: API off, saved data used automatically
{
  const { ctx, page } = await newPage()
  await page.route('**/127.0.0.1:8000/**', (r) => r.abort('connectionrefused'))
  await page.goto(`${BASE}&t=JPM`)
  await page.locator('h1').waitFor({ timeout: 60000 })
  await settle(page)
  await full(page, `34-offline-saved-data-JPM`)
  await ctx.close()
}

// 6. Empty states: TSLA pays no dividend; JPM (a bank) has no gross margin / debt-to-equity
{
  const { ctx, page } = await newPage()
  await page.goto(`${BASE}&t=TSLA&tab=fundamentals`)
  await page.locator('h1').waitFor({ timeout: 120000 })
  await settle(page)
  await expandAll(page)
  await full(page, `35-empty-TSLA-no-dividend`)
  await ctx.close()
}

// 7. Production-safe mode (only licensed data shown)
{
  const { ctx, page } = await newPage()
  await page.goto(`${BASE}&t=${T}&safe=1`)
  await page.locator('h1').waitFor({ timeout: 120000 })
  await settle(page)
  await full(page, `36-${T}-production-safe-mode`)
  await ctx.close()
}

console.log(`${shots.length} screenshots in design/final:\n` + shots.join('\n'))
await browser.close()
