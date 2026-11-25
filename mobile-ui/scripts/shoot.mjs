// Screenshot the prototype at 390 × 844 (phone size) with Playwright, using the installed Chrome.
// Usage:  node scripts/shoot.mjs <outDir> <name> [url]
import { chromium } from 'playwright'

const [outDir = '../design/compare', name = 'proto', url = 'http://127.0.0.1:4173/?statusbar=1'] = process.argv.slice(2)

const browser = await chromium.launch({ channel: 'chrome', headless: true })
const page = await browser.newPage({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 1 })
await page.goto(url, { waitUntil: 'networkidle' })
await page.evaluate(() => document.fonts.ready)
await page.waitForTimeout(600)
await page.screenshot({ path: `${outDir}/${name}-screen.png` })
await page.screenshot({ path: `${outDir}/${name}-full.png`, fullPage: true })
const h = await page.evaluate(() => document.documentElement.scrollHeight)
console.log(`saved ${name}: full page height ${h}px`)
await browser.close()
