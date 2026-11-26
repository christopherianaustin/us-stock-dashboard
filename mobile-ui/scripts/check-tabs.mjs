// Open the prototype at 390 × 844, visit every tab, open every collapsed card, and screenshot it.
// Reports console errors, "Couldn't load" sections and where data came from (live API / saved data).
// Usage: node scripts/check-tabs.mjs <outDir> <TICKER> [mode=auto|live|mock] [extra query]
import { chromium } from 'playwright'

const [outDir = '../design/compare', ticker = 'AAPL', mode = 'auto', extra = ''] = process.argv.slice(2)
const TABS = ['Analysis', 'Fundamentals', 'News', 'Financials', 'Technicals', 'About']
const url = `http://127.0.0.1:4173/?statusbar=1&t=${ticker}&mode=${mode}${extra ? '&' + extra : ''}`

const browser = await chromium.launch({ channel: 'chrome', headless: true })
const page = await browser.newPage({ viewport: { width: 390, height: 844 } })
const errors = []
page.on('pageerror', (e) => errors.push('pageerror: ' + e.message))
page.on('console', (m) => { if (m.type() === 'error' && !/finnhub|favicon|ERR_CONNECTION_REFUSED|Failed to load resource/.test(m.text())) errors.push(m.text()) })

const t0 = Date.now()
await page.goto(url, { waitUntil: 'domcontentloaded' })
await page.locator('h1').waitFor({ timeout: 120000 })
const firstScreen = Date.now() - t0
const report = { ticker, mode, firstScreenMs: firstScreen, tabs: {} }

for (const [ti, tab] of TABS.entries()) {
  await page.locator('[role="tab"]').nth(ti).click()
  // wait until no skeletons are left (or 90 s)
  await page.waitForFunction(() => !document.querySelector('[data-skeleton]'), null, { timeout: 90000 }).catch(() => {})
  for (let i = 0; i < 12 && await page.locator('[data-toggle="closed"]').count(); i++) await page.locator('[data-toggle="closed"]').first().click()
  await page.waitForFunction(() => !document.querySelector('[data-skeleton]'), null, { timeout: 90000 }).catch(() => {})
  await page.waitForTimeout(700)
  const failed = await page.locator('[data-section-error]').count()
  const na = await page.locator('text=/^N\\/A/').count()
  report.tabs[tab] = { failedSections: failed, naValues: na }
  const main = page.locator('main')
  const box = await main.boundingBox()
  // make the window as tall as the page so every chart is really drawn, then screenshot, then go back to 844
  const fullH = await page.evaluate(() => document.documentElement.scrollHeight)
  await page.setViewportSize({ width: 390, height: fullH })
  await page.waitForTimeout(600)
  await page.screenshot({ path: `${outDir}/${ticker}-${mode}-${tab.toLowerCase()}.png` })
  await page.setViewportSize({ width: 390, height: 844 })
  report.tabs[tab].height = Math.round(box?.height ?? 0)
}
report.footer = await page.locator('footer').innerText()
report.errors = errors
console.log(JSON.stringify(report, null, 1))
await browser.close()
