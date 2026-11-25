import { useEffect, useRef, useState } from 'react'
import { MOCK_USD_IDR } from './config'
import { SettingsProvider, ep, useData, useRate, useSettings } from './lib/data'
import { dateShort, num, shortName } from './lib/format'
import { useT, type TKey } from './lib/i18n'
import { BuySell, PriceChart, SmallHeader, StatusBar, TopInfo, type Header } from './components/Top'
import { HoldingCard } from './components/Cards'
import { DebugMenu } from './components/DebugMenu'
import { Divider, SheetProvider, Toast } from './components/ui'
import { AnalysisTab } from './tabs/AnalysisTab'
import { FundamentalsTab } from './tabs/FundamentalsTab'
import { NewsTab } from './tabs/NewsTab'
import { FinancialsTab, StatementPage } from './tabs/FinancialsTab'
import { TechnicalsTab } from './tabs/TechnicalsTab'
import { AboutTab } from './tabs/AboutTab'

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
  const sum = useData<any>(ep.summary)
  const tech = useData<any>(ep.technicals)
  const { rate, asOf, kind } = useRate(MOCK_USD_IDR)
  const [tab, setTab] = useState<Tab>(() => (new URLSearchParams(location.search).get('tab') as Tab) || 'analysis')
  const [toast, setToast] = useState<string | null>(null)
  const [statement, setStatement] = useState<'quarterly' | 'annual' | null>(null)
  const [debug, setDebug] = useState(false)
  const taps = useRef<number[]>([])
  const sentinel = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!toast) return
    const id = setTimeout(() => setToast(null), 2000)
    return () => clearTimeout(id)
  }, [toast])

  const h = sum.data?.header
  const header: Header | null = h ? {
    ticker: s.ticker, name: shortName(h.name?.value ?? s.ticker), logo: h.logo_url?.value,
    priceUsd: h.price?.value ?? null, changePct: h.change_pct?.value ?? null, priceTag: h.price?.license_tag,
    priceNa: h.price?.na_reason, earningsDate: h.next_earnings_date?.value ?? null,
  } : null
  const priceUsd = header?.priceUsd ?? null
  const rateLine = `1 USD = Rp ${num(rate)} · ${kind === 'live' ? dateShort(asOf) : kind === 'saved' ? `saved rate, ${dateShort(asOf)}` : 'Mock rate'}`

  const tapTicker = () => {
    const now = Date.now()
    taps.current = [...taps.current.filter((x) => now - x < 2500), now]
    if (taps.current.length >= 5) { taps.current = []; setDebug(true) }
  }
  const pickTab = (k: Tab) => {
    setTab(k)
    // keep the reading position, unless the tab row has scrolled out of view
    const el = sentinel.current
    if (el && el.getBoundingClientRect().top < (statusBar ? 0 : 0)) el.scrollIntoView({ block: 'start' })
  }

  return (
    <div className="phone-scroll">
      {statusBar && <StatusBar />}
      <SmallHeader onTap={setToast} />
      {sum.error && !sum.data ? (
        <div className="px-6 py-10 text-center">
          <p className="t-subtitle text-navy m-0">Couldn't load {s.ticker}</p>
          <p className="t-label-m text-dgrey mt-2">{sum.error}</p>
          <button type="button" onClick={sum.retry} className="mt-4 h-10 px-6 rounded-full bg-ink text-white t-label border-0 cursor-pointer">Try again</button>
          <p className="t-action text-dgrey mt-6">Tap here 5 times to pick another stock</p>
          <button type="button" onClick={tapTicker} className="t-link text-purple bg-transparent border-0 cursor-pointer">{s.ticker}</button>
        </div>
      ) : (
        <>
          <TopInfo h={header} rate={rate} rateLine={rateLine} onTicker={tapTicker} />
          <PriceChart q={tech} rate={rate} onToast={setToast} />
          <BuySell onTap={() => setToast('Prototype only')} />
          <div className="mt-6"><Divider /></div>
          {priceUsd != null && <div className="px-6 pt-6"><HoldingCard priceUsd={priceUsd} rate={rate} /></div>}

          <div ref={sentinel} className="h-6 scroll-mt-0" />
          {/* Pill tabs: stick to the top while scrolling */}
          <nav className="sticky top-0 z-20 bg-white/95 backdrop-blur py-3 border-b border-lgrey">
            <div role="tablist" aria-label="Sections" className="flex gap-2 overflow-x-auto no-scrollbar px-6">
              {TABS.map((k) => (
                <button key={k} type="button" role="tab" aria-selected={tab === k} onClick={() => pickTab(k)}
                  className={`h-9 px-4 rounded-full whitespace-nowrap t-label border cursor-pointer shrink-0 transition-colors ${tab === k ? 'bg-purple border-purple text-white' : 'bg-white border-grey2 text-dgrey'}`}>
                  {t(k)}
                </button>
              ))}
            </div>
          </nav>

          <main key={`${tab}-${s.ticker}`} className="tab-fade flex flex-col gap-6 px-6 pt-5 pb-6" role="tabpanel">
            {tab === 'analysis' && <AnalysisTab rate={rate} priceUsd={priceUsd} />}
            {tab === 'fundamentals' && <FundamentalsTab rate={rate} priceUsd={priceUsd} />}
            {tab === 'news' && <NewsTab />}
            {tab === 'financials' && <FinancialsTab rate={rate} onFullStatement={setStatement} />}
            {tab === 'technicals' && <TechnicalsTab rate={rate} />}
            {tab === 'about' && <AboutTab rate={rate} />}
          </main>

          <footer className="px-6 pb-10">
            <p className="t-action text-dgrey m-0">{t('disclaimer')}</p>
            <p className="t-action text-grey mt-2 mb-0">
              {sum.src === 'mock' ? `Saved data from ${dateShort(sum.env?.generated_at)} (mock mode)` : 'Live data from the demo API'}
              {s.safe ? ' · production-safe mode' : ''} · Charts by TradingView Lightweight Charts
            </p>
          </footer>
        </>
      )}
      {statement && <StatementPage period={statement} rate={rate} onClose={() => setStatement(null)} />}
      {debug && <DebugMenu onClose={() => setDebug(false)} src={sum.src} />}
      <Toast text={toast} />
    </div>
  )
}
