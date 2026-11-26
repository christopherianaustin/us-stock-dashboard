import { Suspense, lazy, useEffect, useRef, useState } from 'react'
import { MOCK_TICKERS, MOCK_USD_IDR, QUICK_TICKERS } from './config'
import { SettingsProvider, ep, errorText, prefetch, useData, useRate, useSettings } from './lib/data'
import { dateShort, num, shortName } from './lib/format'
import { useL, useT, type TKey } from './lib/i18n'
import { BuySell, PriceChart, SmallHeader, StatusBar, TopInfo, type Header } from './components/Top'
import { HoldingCard } from './components/Cards'
import { Divider, SheetProvider, Skeleton, Toast } from './components/ui'

// Each tab's code (and the chart library it uses) is downloaded only when needed, so the first screen loads faster.
const AnalysisTab = lazy(() => import('./tabs/AnalysisTab').then((m) => ({ default: m.AnalysisTab })))
const FundamentalsTab = lazy(() => import('./tabs/FundamentalsTab').then((m) => ({ default: m.FundamentalsTab })))
const NewsTab = lazy(() => import('./tabs/NewsTab').then((m) => ({ default: m.NewsTab })))
const FinancialsTab = lazy(() => import('./tabs/FinancialsTab').then((m) => ({ default: m.FinancialsTab })))
const StatementPage = lazy(() => import('./tabs/FinancialsTab').then((m) => ({ default: m.StatementPage })))
const TechnicalsTab = lazy(() => import('./tabs/TechnicalsTab').then((m) => ({ default: m.TechnicalsTab })))
const AboutTab = lazy(() => import('./tabs/AboutTab').then((m) => ({ default: m.AboutTab })))
const DebugMenu = lazy(() => import('./components/DebugMenu').then((m) => ({ default: m.DebugMenu })))

const TABS = ['analysis', 'fundamentals', 'news', 'financials', 'technicals', 'about'] as const satisfies readonly TKey[]
type Tab = (typeof TABS)[number]

const wideScreen = () => window.matchMedia('(min-width: 520px)').matches

export default function App() {
  const [framed, setFramed] = useState(wideScreen)
  useEffect(() => {
    const mq = window.matchMedia('(min-width: 520px)')
    const on = () => setFramed(mq.matches)
    mq.addEventListener('change', on)
    return () => mq.removeEventListener('change', on)
  }, [])
  return (
    <SettingsProvider>
      <div className="phone-stage">
        <div className="phone">
          <SheetProvider>
            <Page statusBar={framed || new URLSearchParams(location.search).has('statusbar')} />
          </SheetProvider>
        </div>
      </div>
    </SettingsProvider>
  )
}

function Page({ statusBar }: { statusBar: boolean }) {
  const s = useSettings()
  const t = useT()
  const L = useL()
  const sum = useData<any>(ep.summary)
  const tech = useData<any>(ep.technicals)
  const { rate, asOf, kind } = useRate(MOCK_USD_IDR)
  const [tab, setTab] = useState<Tab>(() => {
    const q = new URLSearchParams(location.search).get('tab') as Tab
    return TABS.includes(q) ? q : 'analysis'
  })
  const [toast, setToast] = useState<string | null>(null)
  const [statement, setStatement] = useState<'quarterly' | 'annual' | null>(null)
  const [debug, setDebug] = useState(false)
  const taps = useRef<number[]>([])
  const sentinel = useRef<HTMLDivElement>(null)
  const tabRow = useRef<HTMLDivElement>(null)
  const proto = L('Prototype only', 'Hanya prototipe')

  useEffect(() => { document.documentElement.lang = s.lang }, [s.lang])

  useEffect(() => {
    if (!toast) return
    const id = setTimeout(() => setToast(null), 2000)
    return () => clearTimeout(id)
  }, [toast])

  // The first load of a stock the API hasn't seen yet can take a while: say so after 3 seconds.
  const [slow, setSlow] = useState(false)
  useEffect(() => {
    setSlow(false)
    if (!sum.loading) return
    const id = setTimeout(() => setSlow(true), 3000)
    return () => clearTimeout(id)
  }, [sum.loading, s.ticker])

  // Once the first screen is ready, quietly load the other tabs so switching feels instant.
  const firstReady = !!sum.data && !tech.loading
  useEffect(() => {
    if (!firstReady) return
    const run = () => {
      for (const m of [import('./tabs/FundamentalsTab'), import('./tabs/NewsTab'), import('./tabs/FinancialsTab'),
        import('./tabs/TechnicalsTab'), import('./tabs/AboutTab')]) m.catch(() => {})
      prefetch(s.ticker, [
      ep.ratios(s.ticker), ep.valuation(s.ticker), ep.ownership(s.ticker), ep.profile(s.ticker), ep.news(s.ticker),
      ep.dividends(s.ticker), ep.earnings(s.ticker), ep.financials(s.ticker, 'quarterly', 'income'),
      ep.financials(s.ticker, 'quarterly', 'cashflow'), ep.financials(s.ticker, 'quarterly', 'balance'),
      ], s.mode, s.safe)
    }
    const w = window as any
    const id = w.requestIdleCallback ? w.requestIdleCallback(run, { timeout: 1500 }) : setTimeout(run, 300)
    return () => (w.cancelIdleCallback ? w.cancelIdleCallback(id) : clearTimeout(id))
  }, [firstReady, s.ticker, s.mode, s.safe])

  // keep the selected pill visible in the sideways-scrolling row
  useEffect(() => {
    const row = tabRow.current
    const b = row?.querySelector<HTMLElement>('[aria-selected="true"]')
    if (row && b) row.scrollTo({ left: b.offsetLeft - (row.clientWidth - b.offsetWidth) / 2, behavior: 'smooth' })
  }, [tab, sum.data != null])

  const h = sum.data?.header
  const header: Header | null = h ? {
    ticker: s.ticker, name: shortName(h.name?.value ?? s.ticker), logo: h.logo_url?.value,
    priceUsd: h.price?.value ?? null, changePct: h.change_pct?.value ?? null, priceTag: h.price?.license_tag,
    priceNa: h.price?.na_reason, earningsDate: h.next_earnings_date?.value ?? null,
  } : null
  const priceUsd = header?.priceUsd ?? null
  const rateLine = `1 USD = Rp ${num(rate)} · ${kind === 'live' ? dateShort(asOf) : kind === 'saved' ? `${L('saved rate', 'kurs tersimpan')}, ${dateShort(asOf)}` : L('Mock rate', 'Kurs contoh')}`

  const tapTicker = () => {
    const now = Date.now()
    taps.current = [...taps.current.filter((x) => now - x < 2500), now]
    if (taps.current.length >= 5) { taps.current = []; setDebug(true) }
  }
  const pickTab = (k: Tab) => {
    setTab(k)
    const u = new URL(location.href); u.searchParams.set('tab', k); history.replaceState(null, '', u)
    // keep the reading position, unless the tab row has scrolled out of view
    const el = sentinel.current
    if (el && el.getBoundingClientRect().top < 0) el.scrollIntoView({ block: 'start' })
  }
  const err = errorText(sum.errKind, s.lang, s.ticker)
  const picks = (sum.errKind === 'api_down' || sum.errKind === 'no_saved' ? [...MOCK_TICKERS] : [...QUICK_TICKERS]).filter((x) => x !== s.ticker)

  return (
    <div className="phone-scroll">
      {statusBar && <StatusBar />}
      <SmallHeader onTap={() => setToast(proto)} />
      {sum.error && !sum.data ? (
        <div className="px-6 pt-12 pb-10 text-center" role="alert">
          <div className="mx-auto size-16 rounded-full bg-lavender grid place-items-center">
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none" aria-hidden><path d="M12 8v5m0 3.5v.5M10.3 3.9 2.6 17a2 2 0 0 0 1.7 3h15.4a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z" stroke="#561FA3" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg>
          </div>
          <p className="t-subtitle text-navy mt-4 mb-0">{err.title}</p>
          <p className="t-label-m text-dgrey mt-2 mb-0">{err.body}</p>
          <button type="button" onClick={sum.retry} className="mt-5 h-11 px-8 rounded-full bg-ink text-white t-label border-0 cursor-pointer">{L('Try again', 'Coba lagi')}</button>
          {picks.length > 0 && (
            <>
              <p className="t-label text-navy mt-8 mb-0">{L('Or open another stock', 'Atau buka saham lain')}</p>
              <div className="flex flex-wrap justify-center gap-2 mt-3">
                {picks.map((x) => <button key={x} type="button" onClick={() => s.setTicker(x)}
                  className="t-label-m text-navy bg-white border border-grey2 rounded-full px-4 py-1 cursor-pointer">{x}</button>)}
              </div>
            </>
          )}
          <p className="t-action text-grey mt-8 mb-0 break-words">{sum.error}</p>
          {/* tap 5 times for the prototype settings, like the ticker on the normal page */}
          <button type="button" onClick={tapTicker} className="t-action text-grey bg-transparent border-0 cursor-default mt-1">{s.ticker}</button>
        </div>
      ) : (
        <>
          <TopInfo h={header} rate={rate} rateLine={rateLine} onTicker={tapTicker} />
          {slow && sum.loading && (
            <p className="px-6 mt-3 mb-0 t-action text-dgrey" role="status">
              {L(`Getting the latest data for ${s.ticker}… The first load of a stock can take up to 20 seconds.`,
                `Mengambil data terbaru untuk ${s.ticker}… Pemuatan pertama sebuah saham bisa sampai 20 detik.`)}
            </p>
          )}
          <PriceChart q={tech} rate={rate} onToast={setToast} />
          <BuySell onTap={() => setToast(proto)} />
          <div className="mt-6"><Divider /></div>
          {priceUsd != null && <div className="px-6 pt-6"><HoldingCard priceUsd={priceUsd} rate={rate} /></div>}

          <div ref={sentinel} className="h-6 scroll-mt-0" />
          {/* Pill tabs: stick to the top while scrolling */}
          <nav className="sticky top-0 z-20 bg-white/95 backdrop-blur py-3 border-b border-lgrey">
            <div ref={tabRow} role="tablist" aria-label={L('Sections', 'Bagian')} className="flex gap-2 overflow-x-auto no-scrollbar px-6">
              {TABS.map((k) => (
                <button key={k} type="button" role="tab" aria-selected={tab === k} onClick={() => pickTab(k)}
                  className={`h-9 px-4 rounded-full whitespace-nowrap t-label border cursor-pointer shrink-0 ${tab === k ? 'bg-purple border-purple text-white' : 'bg-white border-grey2 text-dgrey'}`}>
                  {t(k)}
                </button>
              ))}
            </div>
          </nav>

          <main key={`${tab}-${s.ticker}-${s.lang}`} className="tab-fade flex flex-col gap-6 px-6 pt-5 pb-6" role="tabpanel">
            <Suspense fallback={<><Skeleton h={220} /><Skeleton h={160} /></>}>
              {tab === 'analysis' && <AnalysisTab rate={rate} priceUsd={priceUsd} />}
              {tab === 'fundamentals' && <FundamentalsTab rate={rate} priceUsd={priceUsd} />}
              {tab === 'news' && <NewsTab />}
              {tab === 'financials' && <FinancialsTab rate={rate} onFullStatement={setStatement} />}
              {tab === 'technicals' && <TechnicalsTab rate={rate} />}
              {tab === 'about' && <AboutTab rate={rate} onToast={setToast} />}
            </Suspense>
          </main>

          <footer className="px-6 pb-10">
            <p className="t-action text-dgrey m-0">{t('disclaimer')}</p>
            <p className="t-action text-grey mt-2 mb-0">
              {sum.src === 'mock'
                ? L(`Saved data from ${dateShort(sum.env?.generated_at)} (${s.mode === 'mock' ? 'saved-data mode' : 'API offline'})`,
                  `Data tersimpan dari ${dateShort(sum.env?.generated_at)} (${s.mode === 'mock' ? 'mode data tersimpan' : 'API offline'})`)
                : L('Live data from the demo API', 'Data langsung dari API demo')}
              {s.safe ? L(' · production-safe mode', ' · mode aman produksi') : ''} · {L('Charts by TradingView Lightweight Charts', 'Grafik oleh TradingView Lightweight Charts')}
            </p>
          </footer>
        </>
      )}
      <Suspense fallback={null}>
        {statement && <StatementPage period={statement} rate={rate} onClose={() => setStatement(null)} />}
        {debug && <DebugMenu onClose={() => setDebug(false)} src={sum.src} />}
      </Suspense>
      <Toast text={toast} />
    </div>
  )
}
