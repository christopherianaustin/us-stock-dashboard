import type React from 'react'
import { useState } from 'react'
import { dateShort, num, pctAbs, pctSigned, rp, rpShort } from '../lib/format'
import { useT } from '../lib/i18n'
import { Badge, Card, ChangeIcon, Row } from './ui'
import portfolioIcon from '../assets/figma/portfolio-icon.svg'
import badgeShares from '../assets/figma/badge-shares.svg'
import badgeAvg from '../assets/figma/badge-avgcost.svg'
import badgeReturn from '../assets/figma/badge-return.svg'
import badgeReturnPct from '../assets/figma/badge-returnpct.svg'

/** Figma "Icon badge": 24 px box; the SVG includes its soft shadow, so it overflows the box. */
const IconBadge = ({ src }: { src: string }) => (
  <span className="relative size-6 shrink-0">
    <img src={src} alt="" className="absolute max-w-none" style={{ left: -7, top: -5, width: 38, height: 38 }} />
  </span>
)

/* ---------- My Holding (example numbers: there is no portfolio data in this prototype) ---------- */
export function HoldingCard({ priceUsd, rate }: { priceUsd: number; rate: number }) {
  // Example only: about Rp 10 million invested, bought 5% below today's price.
  const avgCostUsd = priceUsd * 0.95
  const shares = Math.round((10_000_000 / rate / avgCostUsd) * 10000) / 10000
  const value = shares * priceUsd
  const ret = (priceUsd - avgCostUsd) * shares
  const retPct = (priceUsd / avgCostUsd - 1) * 100
  const up = ret >= 0
  return (
    <Card title="My Holding"
      extra={<span className="t-action-b text-dgrey bg-grey2 rounded-full px-2 py-0.5">Example holding</span>}>
      <div className="flex gap-4">
        <span className="relative size-12 shrink-0">
          <img src={portfolioIcon} alt="" className="absolute max-w-none" style={{ left: 4, top: 4, width: 44.4, height: 46.6 }} />
        </span>
        <div>
          <div className="t-label-m text-dgrey">My Current Portfolio</div>
          <div className="t-title text-navy mt-0.5">{rp(value, rate)}</div>
        </div>
      </div>
      <div className="flex flex-col gap-4 mt-6">
        <Row icon={<IconBadge src={badgeShares} />} label="Shares" value={num(shares, 4)} />
        <Row icon={<IconBadge src={badgeAvg} />} label="Avg. Cost" value={rp(avgCostUsd, rate)} />
        <Row icon={<IconBadge src={badgeReturn} />} label="Total Return"
          value={<><ChangeIcon up={up} /><span className="text-dgrey">{rp(Math.abs(ret), rate)}</span></>} />
        <Row icon={<IconBadge src={badgeReturnPct} />} label="Total Return %"
          value={<><ChangeIcon up={up} /><span className="text-dgrey">{pctAbs(retPct)}</span></>} />
      </div>
    </Card>
  )
}

/* ---------- Company details ---------- */
export type CompanyRow = { label: string; value: React.ReactNode }
export function CompanyCard({ legalName, ticker, description, rows }: {
  legalName: string; ticker: string; description: string; rows: CompanyRow[]
}) {
  const [more, setMore] = useState(false)
  return (
    <Card title={`${legalName} | ${ticker}`}>
      <div className="relative">
        <p className={`t-body text-navy m-0 ${more ? '' : 'line-clamp-4'}`}>
          {description}
          {more && <> <button type="button" onClick={() => setMore(false)} className="t-label text-purple bg-transparent border-0 p-0 cursor-pointer">Read less</button></>}
        </p>
        {!more && (
          <button type="button" onClick={() => setMore(true)}
            className="absolute right-0 bottom-0 bg-white pl-0.5 t-label text-purple border-0 p-0 cursor-pointer h-[26px] flex items-baseline">
            <span className="t-body text-navy mr-1">..</span>Read more
          </button>
        )}
      </div>
      <div className="flex flex-col gap-4 mt-6">
        {rows.map((r) => <Row key={r.label} label={r.label} value={r.value} />)}
      </div>
    </Card>
  )
}

/* ---------- Analyst ratings (Wall Street analysts, not Nanovest) ---------- */
const RATING_LABELS = ['Strong buy', 'Buy', 'Hold', 'Sell', 'Strong sell']
const AXIS = [['Strong', 'Buy'], ['Buy'], ['Hold'], ['Sell'], ['Strong', 'Sell']]

export function AnalystCard({ ticker, counts, tag }: { ticker: string; counts: number[]; tag?: string | null }) {
  const t = useT()
  const total = counts.reduce((a, b) => a + b, 0)
  const mean = counts.reduce((a, c, i) => a + c * (i + 1), 0) / total
  const pos = ((mean - 1) / 4) * 100
  const top = counts.indexOf(Math.max(...counts))
  return (
    <>
      <p className="t-body text-navy m-0">
        What analysts rate {ticker}’s shares on a scale from 1 (buy) to 3 (hold) to 5 (sell)
      </p>
      <p className="t-action text-dgrey mt-1 mb-0">{t('wall_street')} <Badge tag={tag} /></p>

      {/* slider: 8 px track, white dots, hollow end dots, knob with a lavender ring */}
      <div className="relative h-[52px] mt-[23px]">
        <div className="absolute left-0 right-0 top-[39px] h-2 rounded-full"
          style={{ background: 'linear-gradient(90deg,#0B6B3A 0%,#1E5A3A 30%,#4A2A1E 60%,#B0141A 100%)' }} />
        {[0, 25, 50, 75, 100].map((x) => (
          <span key={x}
            className={`absolute top-[40px] size-1.5 rounded-full bg-white ${x === 0 ? 'left-[1px]' : x === 100 ? 'right-[1px]' : '-translate-x-1/2'}`}
            style={x > 0 && x < 100 ? { left: `${x}%` } : undefined} />
        ))}
        <div className="absolute top-0 -translate-x-1/2 flex flex-col items-center" style={{ left: `clamp(16px, ${pos}%, calc(100% - 16px))` }}>
          <span className="bg-purple text-white t-action-b rounded px-1.5 py-0.5">{num(mean, 1)}</span>
          <span className="w-0 h-0 border-x-4 border-x-transparent border-t-4 border-t-purple" />
          <span className="size-[26px] rounded-full bg-purple shadow-[0_0_0_4px_#DCD0F7] mt-[6px]" />
        </div>
      </div>
      <div className="relative h-8 mt-1.5 t-action text-navy">
        {AXIS.map((lines, i) => (
          <span key={i} className={`absolute top-0 leading-4 ${i === 0 ? 'left-0 text-left' : i === 4 ? 'right-0 text-right' : '-translate-x-1/2 text-center'}`}
            style={i > 0 && i < 4 ? { left: `${i * 25}%` } : undefined}>
            {lines.map((l) => <span key={l} className="block">{l}</span>)}
          </span>
        ))}
      </div>

      <p className="t-body text-dgrey mt-6 mb-0">Based on {total} reviews</p>
      <div className="flex flex-col gap-1 mt-4">
        {counts.map((c, i) => {
          const p = (c / total) * 100
          return (
            <div key={i} className="flex items-center gap-3 h-5">
              <div className="w-[61%] h-2 rounded-lg bg-grey2 overflow-hidden shrink-0">
                <div className="h-2 rounded-lg bg-purple" style={{ width: `max(8px, ${p}%)` }} />
              </div>
              <span className={`t-label flex-1 text-right whitespace-nowrap ${i === top ? 'text-purple' : 'text-grey'}`}>
                {num(p)}% {RATING_LABELS[i]}
              </span>
            </div>
          )
        })}
      </div>
    </>
  )
}

/* ---------- Price Target Forecast ---------- */
function niceStep(raw: number) {
  const p = 10 ** Math.floor(Math.log10(raw))
  const f = raw / p
  return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 2.5 ? 2.5 : f <= 5 ? 5 : 10) * p
}

type Callout = { key: string; title: string; usd: number; bg: string; line: string; dash: string }

export function ForecastCard({ name, cur, lowUsd, meanUsd, highUsd, updated, rate, tag }: {
  name: string; cur: number; lowUsd: number; meanUsd: number; highUsd: number; updated: string; rate: number; tag?: string | null
}) {
  const [mode, setMode] = useState<'rp' | 'pct'>('rp')

  // Axis: 5 evenly spaced ticks that cover low … high (and today's price).
  const lo = Math.min(lowUsd, cur), hi = Math.max(highUsd, cur)
  let step = niceStep((hi - lo) / 4)
  let minT = Math.floor(lo / step) * step
  while (minT + 4 * step < hi) { step = niceStep(step * 1.01); minT = Math.floor(lo / step) * step }
  const maxT = minT + 4 * step
  // Content box (Figma): labels every 48 px, centers at 8 … 200
  const y = (usd: number) => 8 + ((maxT - usd) / (maxT - minT)) * 192
  const fmt = (usd: number) => (mode === 'rp' ? rp(usd, rate) : pctSigned((usd / cur - 1) * 100))
  const tick = (usd: number) => (mode === 'rp' ? rpShort(usd * rate, usd * rate < 1e6 ? 0 : 1).replace('.0 ', ' ') : pctSigned((usd / cur - 1) * 100).replace('.00', ''))

  const right: Callout[] = [
    { key: 'high', title: 'High', usd: highUsd, bg: '#06CB90', line: '#06CB90', dash: '3 3' },
    { key: 'target', title: 'Target', usd: meanUsd, bg: '#561FA3', line: '#561FA3', dash: '3 3' },
    { key: 'low', title: 'Low', usd: lowUsd, bg: '#E11C23', line: '#E11C23', dash: '1.5 3' },
  ]
  // keep the right-hand labels from overlapping (each is 36 px tall)
  const ys = right.map((c) => y(c.usd))
  for (let i = 1; i < ys.length; i++) if (ys[i] - ys[i - 1] < 38) ys[i] = ys[i - 1] + 38
  const yc = y(cur)
  const W = 278 // content width at 390 px screen (card 342 − 2×16 zone inset − 2×16 content inset)
  const curDotX = 136 // left edge of the "Current" dot (label ≈ 78 px + arrow + gap)
  const rightDotX = W - 96 // leaves room for the widest right-hand label

  return (
    <>
      <p className="t-body text-navy m-0 px-4">
        Analysts’ estimates of what could happen to {name}’s share price over the next 12 months
      </p>
      <div className="mt-4 pb-4" style={{ background: 'linear-gradient(92.3deg,#F7F3FF 0%,#EEF7FF 96.9%)' }}>
        <div className="flex items-center gap-4 px-4 pt-4">
          <span className="t-action text-navy flex-1">Updated on {dateShort(updated)} <Badge tag={tag} /></span>
          <div className="flex gap-2">
            {(['rp', 'pct'] as const).map((k) => (
              <button key={k} type="button" onClick={() => setMode(k)}
                className={`rounded-full py-1 px-6 cursor-pointer w-[60px] grid place-items-center ${mode === k ? 'bg-purple text-white t-action-b border border-purple' : 'bg-white text-navy t-action border border-grey2'}`}>
                {k === 'rp' ? 'Rp' : '%'}
              </button>
            ))}
          </div>
        </div>
        <div className="relative mx-4 mt-2 h-[240px] rounded-lg overflow-hidden bg-up-bg">
          <div className="absolute left-0 right-0 bottom-0 bg-down-bg rounded-lg" style={{ top: 23 + yc }} />
          <div className="absolute left-4 right-4 top-[23px] h-[208px]">
            {[0, 1, 2, 3, 4].map((i) => (
              <span key={i} className="absolute left-0 text-[10px] leading-4 font-medium text-navy whitespace-nowrap" style={{ top: i * 48 }}>
                {tick(maxT - i * step)}
              </span>
            ))}
            <svg className="absolute inset-0 overflow-visible" width="100%" height="208" aria-hidden>
              {right.map((c, i) => (
                <line key={c.key} x1={curDotX + 4} y1={yc} x2={rightDotX + 4} y2={ys[i]} stroke={c.line} strokeWidth="1.5" strokeDasharray={c.dash} />
              ))}
            </svg>
            {/* Current (left) */}
            <div className="absolute flex items-center -translate-y-1/2" style={{ left: 48, top: yc }}>
              <div className="rounded px-1 py-0.5 text-white text-[10px] leading-4 font-bold whitespace-nowrap"
                style={{ background: 'linear-gradient(94.3deg,#B386FF 0%,#52B1FE 96.9%)' }}>
                <div>Current</div><div>{mode === 'rp' ? rp(cur, rate) : '0%'}</div>
              </div>
              <span className="w-0 h-0 border-y-4 border-y-transparent border-l-[6px] border-l-[#52B1FE]" />
              <span className="size-2 rounded-full bg-[#7E9BFE] ml-1" />
            </div>
            {/* High / Target / Low (right) */}
            {right.map((c, i) => (
              <div key={c.key} className="absolute flex items-center -translate-y-1/2" style={{ left: rightDotX, top: ys[i] }}>
                <span className="size-2 rounded-full mr-1" style={{ background: c.bg }} />
                <span className="w-0 h-0 border-y-4 border-y-transparent border-r-[6px]" style={{ borderRightColor: c.bg }} />
                <div className="rounded px-1 py-0.5 text-white text-[10px] leading-4 font-bold whitespace-nowrap" style={{ background: c.bg }}>
                  <div>{c.title}</div><div>{fmt(c.usd)}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </>
  )
}
