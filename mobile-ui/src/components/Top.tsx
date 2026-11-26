import { useEffect, useMemo, useRef, useState } from 'react'
import { ColorType, LineSeries, LineType, createChart } from 'lightweight-charts'
import { dateShort, num, pctAbs, rp } from '../lib/format'
import { useL, useT } from '../lib/i18n'
import type { Q } from '../lib/data'
import { BackIcon, Badge, BellIcon, ChangeIcon, HeartIcon, InfoIcon, ShareIcon, Skeleton } from './ui'

/* ---------- iOS status bar (only drawn inside the desktop phone frame / screenshots) ---------- */
export function StatusBar() {
  return (
    <div className="h-11 flex items-center justify-between pl-8 pr-6 text-[15px] font-bold text-black" aria-hidden>
      <span>9:41</span>
      <span className="flex items-center gap-1.5">
        <svg width="18" height="11" viewBox="0 0 18 11"><g fill="#000"><rect x="0" y="7" width="3" height="4" rx="1" /><rect x="5" y="5" width="3" height="6" rx="1" /><rect x="10" y="2.5" width="3" height="8.5" rx="1" /><rect x="15" y="0" width="3" height="11" rx="1" /></g></svg>
        <svg width="16" height="11" viewBox="0 0 16 11"><path fill="#000" d="M8 2.2c2.3 0 4.4.9 6 2.4l1.2-1.2A10 10 0 0 0 8 .5 10 10 0 0 0 .8 3.4L2 4.6a8.4 8.4 0 0 1 6-2.4zm0 3.4c1.4 0 2.6.5 3.6 1.4l1.2-1.2A6.8 6.8 0 0 0 8 3.9a6.8 6.8 0 0 0-4.8 1.9L4.4 7A5.1 5.1 0 0 1 8 5.6zm0 3.3c.5 0 1 .2 1.3.6L8 10.8 6.7 9.5c.3-.4.8-.6 1.3-.6z" /></svg>
        <svg width="26" height="12" viewBox="0 0 26 12"><rect x=".5" y=".5" width="22" height="11" rx="3.5" fill="none" stroke="#000" opacity=".35" /><rect x="2" y="2" width="19" height="8" rx="2" fill="#000" /><path d="M24 4v4a2 2 0 0 0 0-4z" fill="#000" opacity=".4" /></svg>
      </span>
    </div>
  )
}

/* ---------- Small header: back + favourite, alert, share (58 px) ---------- */
export function SmallHeader({ onTap }: { onTap: () => void }) {
  const L = useL()
  // 24 px icons with a 44 px tap area
  const btn = 'size-6 grid place-items-center bg-transparent border-0 p-0 cursor-pointer relative after:absolute after:-inset-2.5'
  return (
    <div className="h-[58px] flex items-center justify-between px-6">
      <button type="button" className={btn} aria-label={L('Back', 'Kembali')} onClick={onTap}><BackIcon /></button>
      <div className="flex items-center gap-6">
        <button type="button" className={btn} aria-label={L('Favourite', 'Favorit')} onClick={onTap}><HeartIcon /></button>
        <button type="button" className={btn} aria-label={L('Price alert', 'Notifikasi harga')} onClick={onTap}><BellIcon /></button>
        <button type="button" className={btn} aria-label={L('Share', 'Bagikan')} onClick={onTap}><ShareIcon /></button>
      </div>
    </div>
  )
}

/* ---------- Top info: logo, ticker, name, price, exchange rate, next earnings ---------- */
function Logo({ url, ticker }: { url?: string | null; ticker: string }) {
  const [failed, setFailed] = useState(false)
  useEffect(() => setFailed(false), [url])
  return (
    <div className="size-12 rounded-full bg-ink overflow-hidden grid place-items-center shrink-0">
      {failed || !url ? (
        <span className="text-white t-link">{ticker.replace(/-.*/, '').slice(0, 2)}</span>
      ) : (
        <img src={url} alt="" className="size-12 object-cover" onError={() => setFailed(true)} />
      )}
    </div>
  )
}

export type Header = {
  ticker: string; name: string; logo?: string | null; priceUsd: number | null; changePct: number | null
  priceTag?: string | null; priceNa?: string | null; earningsDate?: string | null
}

export function TopInfo({ h, rate, rateLine, onTicker }: {
  h: Header | null; rate: number; rateLine: string; onTicker: () => void
}) {
  const t = useT()
  const L = useL()
  if (!h) return (
    <div className="px-6"><Skeleton h={48} className="w-48" /><Skeleton h={32} className="w-40 mt-2" /><Skeleton h={28} className="w-56 mt-1" /></div>
  )
  const up = (h.changePct ?? 0) >= 0
  const days = h.earningsDate ? Math.round((new Date(`${h.earningsDate}T00:00:00`).getTime() - Date.now()) / 864e5) : null
  return (
    <div className="px-6">
      <div className="flex items-center gap-2">
        <Logo url={h.logo} ticker={h.ticker} />
        {/* tap the ticker 5 times to open the hidden debug menu */}
        <button type="button" onClick={onTicker} className="t-link text-dgrey bg-transparent border-0 p-0 cursor-default select-none">{h.ticker}</button>
      </div>
      <h1 className="t-title text-dgrey mt-2 mb-0">{h.name}</h1>
      <div className="flex items-center gap-2 mt-1 flex-wrap">
        {h.priceUsd == null ? (
          <span className="t-label-m text-grey">{L('Price', 'Harga')}: {h.priceNa ?? 'N/A'}</span>
        ) : (
          <>
            <span className="t-subtitle text-navy">{rp(h.priceUsd, rate)}</span>
            {h.changePct != null && (
              <span className="flex items-center gap-1">
                <ChangeIcon up={up} />
                <span className={`t-subtitle ${up ? 'text-up' : 'text-down'}`}>{pctAbs(h.changePct * 100)}</span>
              </span>
            )}
          </>
        )}
        <InfoIcon size={16} topic="price" />
        <Badge tag={h.priceTag} />
      </div>
      <div className="t-action text-dgrey mt-0.5">{rateLine}</div>
      {h.earningsDate && days != null && days >= 0 && (
        <div className="mt-2 inline-flex items-center gap-1.5 rounded-full bg-lgrey px-3 py-1 t-action-b text-navy">
          <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden><rect x="1" y="2" width="10" height="9" rx="2" fill="none" stroke="#561FA3" strokeWidth="1.4" /><path d="M1 5h10M4 1v2M8 1v2" stroke="#561FA3" strokeWidth="1.4" /></svg>
          {t('next_earnings')} {dateShort(h.earningsDate)} · {t('in_days', { n: days })}
        </div>
      )}
    </div>
  )
}

/* ---------- Price line (TradingView Lightweight Charts) + time chips ---------- */
const RANGES = ['1D', '1W', '1M', '1Y', 'All'] as const
type Range = (typeof RANGES)[number]
const BARS: Record<Range, number> = { '1D': 2, '1W': 5, '1M': 21, '1Y': 252, All: 100000 }
type Bar = { date: string; Close: number }

export function PriceChart({ q, rate, onToast }: { q: Q<any>; rate: number; onToast: (m: string) => void }) {
  const L = useL()
  const [range, setRange] = useState<Range>('1Y')
  const box = useRef<HTMLDivElement>(null)
  const [tip, setTip] = useState<string | null>(null)
  const bars: Bar[] = q.data?.bars?.items ?? []
  const data = useMemo(
    () => bars.slice(-BARS[range]).filter((b) => b.Close != null).map((b) => ({ time: b.date, value: b.Close * rate })),
    [bars, range, rate],
  )

  useEffect(() => {
    if (!box.current || data.length < 2) return
    const chart = createChart(box.current, {
      autoSize: true,
      layout: { background: { type: ColorType.Solid, color: '#ffffff' }, textColor: '#7c8d9d', attributionLogo: true },
      grid: { vertLines: { visible: false }, horzLines: { visible: false } },
      rightPriceScale: { visible: false }, leftPriceScale: { visible: false },
      timeScale: { visible: false, borderVisible: false, fixLeftEdge: true, fixRightEdge: true },
      crosshair: { horzLine: { visible: false, labelVisible: false }, vertLine: { labelVisible: false, color: '#a3b1be' } },
      handleScroll: false, handleScale: false,
    })
    const line = chart.addSeries(LineSeries, {
      color: '#111a28', lineWidth: 3, lineType: LineType.Curved, priceLineVisible: false, lastValueVisible: false,
    })
    line.setData(data)
    line.priceScale().applyOptions({ scaleMargins: { top: 0.03, bottom: 0.03 } })
    chart.timeScale().fitContent()
    // tap / drag on the chart shows the exact price
    chart.subscribeCrosshairMove((p) => {
      const d = p.seriesData.get(line) as { value?: number } | undefined
      setTip(d?.value != null && p.time ? `Rp ${num(d.value)} · ${dateShort(String(p.time))}` : null)
    })
    return () => chart.remove()
  }, [data])

  return (
    <div className="pt-4">
      <div className="h-[82px] flex items-end justify-center pb-2">
        {tip && <span className="t-label text-navy bg-lgrey rounded-full px-3 py-1">{tip}</span>}
      </div>
      {q.loading ? <Skeleton h={156} className="mx-6" /> :
        data.length < 2 ? <div className="h-[156px] grid place-items-center t-label-m text-grey px-6 text-center">
          {q.error ? <span>{L('Price history could not be loaded.', 'Riwayat harga gagal dimuat.')}{' '}
            <button type="button" onClick={q.retry} className="t-label text-purple bg-transparent border-0 p-0 cursor-pointer">{L('Try again', 'Coba lagi')}</button></span>
            : (q.data?.bars?.na_reason ?? L('No price history', 'Tidak ada riwayat harga'))}</div> :
          <div ref={box} className="h-[156px] w-full" />}
      <div className="flex justify-center gap-2 mt-[30px]">
        {RANGES.map((r) => (
          <button key={r} type="button" aria-pressed={r === range}
            onClick={() => (r === '1D' ? onToast(L('Intraday prices need a licensed live feed (not in this demo)', 'Harga intraday butuh data live berlisensi (tidak ada di demo ini)')) : setRange(r))}
            className={`t-label rounded-full px-4 pt-1 pb-0.5 border-0 cursor-pointer ${r === range ? 'bg-chip text-navy' : 'bg-transparent text-grey'}`}>
            {r === 'All' ? L('All', 'Semua') : r}
          </button>
        ))}
      </div>
    </div>
  )
}

/* ---------- Buy / Sell: visual only ---------- */
export function BuySell({ onTap }: { onTap: () => void }) {
  const L = useL()
  const cls = 'flex-1 h-12 rounded-full bg-ink text-white t-subtitle border-0 cursor-pointer active:opacity-80'
  return (
    <div className="flex gap-[15px] px-6 mt-6">
      <button type="button" className={cls} onClick={onTap}>{L('Buy', 'Beli')}</button>
      <button type="button" className={cls} onClick={onTap}>{L('Sell', 'Jual')}</button>
    </div>
  )
}
