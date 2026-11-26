import { useEffect, useMemo, useRef, useState } from 'react'
import { CandlestickSeries, ColorType, CrosshairMode, LineSeries, LineStyle, createChart, type ISeriesApi, type SeriesType } from 'lightweight-charts'
import { Bar, BarChart, Cell, Line, LineChart, ReferenceArea, ReferenceLine, XAxis, YAxis } from 'recharts'
import { ep, useData, useSettings } from '../lib/data'
import { dateShort, num, pct, pctSigned, rp, rpShort } from '../lib/format'
import { useL, useT } from '../lib/i18n'
import * as P from '../lib/plain'
import { C, ChartBox, TapTip, axisTick } from '../components/charts'
import { Badge, DataCard, NA, Pills, Row, ToneChip } from '../components/ui'

type BarRow = { date: string; Open: number; High: number; Low: number; Close: number; sma50?: number; sma200?: number; rsi14?: number; macd?: number; signal?: number; hist?: number }
type Level = { price: number; kind: string; strength: number; touches: number; distance: number }
const RANGES = { '1M': 21, '3M': 63, '6M': 126, '1Y': 252, '3Y': 756, '5Y': 1260 } as const
type Range = keyof typeof RANGES

export function TechnicalsTab({ rate }: { rate: number }) {
  const t = useT()
  const L = useL()
  const { lang } = useSettings()
  const q = useData<any>(ep.technicals)

  return (
    <>
      <DataCard q={q} title={t('price_chart')} info="price_chart" h={300} ai="price_technicals">
        {(d) => !d.bars?.available ? <NA reason={d.bars?.na_reason} /> :
          <PriceChart bars={d.bars.items} levels={[...(d.support_resistance?.value?.supports ?? []), ...(d.support_resistance?.value?.resistances ?? [])]} rate={rate} />}
      </DataCard>

      <DataCard q={q} title={t('sr')} info="support_resistance">
        {(d) => {
          const sr = d.support_resistance?.value
          if (!sr) return <NA reason={d.support_resistance?.na_reason} />
          const rows: Level[] = [...sr.resistances].sort((a: Level, b: Level) => b.price - a.price).concat([...sr.supports].sort((a: Level, b: Level) => b.price - a.price))
          return (
            <>
              <div className="grid grid-cols-[1fr_auto_auto] gap-x-3 gap-y-2.5 items-center">
                <span className="t-action-b text-dgrey">{L('Level', 'Level')}</span><span className="t-action-b text-dgrey text-right">{L('From today', 'Dari hari ini')}</span><span className="t-action-b text-dgrey text-right">{L('Strength', 'Kekuatan')}</span>
                {rows.map((l, i) => (
                  <Lvl key={i} l={l} rate={rate} />
                ))}
              </div>
              <p className="t-action text-dgrey mt-3 mb-0">{t('sr_note')} <Badge tag={d.support_resistance.license_tag} /></p>
            </>
          )
        }}
      </DataCard>

      <DataCard q={q} title={t('momentum')} info="rsi" defaultOpen={false}>
        {(d) => <Momentum d={d} />}
      </DataCard>

      <DataCard q={q} title={t('perf')} info="relative_performance" defaultOpen={false}>
        {(d) => {
          const r = d.returns?.value as Record<string, Record<string, number | null>> | null
          if (!r) return <NA reason={d.returns?.na_reason} />
          const keys = Object.keys(r['1Y'] ?? r['1M'] ?? {})
          const [stock, spy, sector] = [keys[0], keys.find((k) => k === 'SPY'), keys.find((k) => k !== keys[0] && k !== 'SPY')]
          const cols = [stock, spy, sector].filter(Boolean) as string[]
          return (
            <div className="grid gap-x-3 gap-y-2.5 items-center" style={{ gridTemplateColumns: `1fr repeat(${cols.length}, auto)` }}>
              <span />{cols.map((c) => <span key={c} className="t-action-b text-dgrey text-right">{c === 'SPY' ? 'S&P 500' : c === stock ? c : `${L('Sector', 'Sektor')} (${c})`}</span>)}
              {['1M', '3M', '6M', 'YTD', '1Y', '3Y', '5Y'].filter((p) => r[p]).map((p) => (
                <Perf key={p} p={p} cols={cols} v={r[p]} />
              ))}
            </div>
          )
        }}
      </DataCard>

      <DataCard q={q} title={t('risk')} info="beta" defaultOpen={false}>
        {(d) => {
          const k = d.risk?.value
          if (!k) return <NA reason={d.risk?.na_reason} />
          const items: [string, string | null, P.Explained][] = [
            ['Beta', k.beta != null ? num(k.beta, 2) : null, P.beta(k.beta, lang)],
            [L('Volatility (1 year)', 'Volatilitas (1 tahun)'), k.volatility_1y != null ? pct(k.volatility_1y, 1) : null, P.volatility(k.volatility_1y, lang)],
            [L('Biggest drop (1 year)', 'Penurunan terbesar (1 tahun)'), k.max_drawdown_1y != null ? pct(k.max_drawdown_1y, 1) : null, P.drawdown(k.max_drawdown_1y, lang)],
            [L('Biggest drop (5 years)', 'Penurunan terbesar (5 tahun)'), k.max_drawdown_5y != null ? pct(k.max_drawdown_5y, 1) : null, P.drawdown(k.max_drawdown_5y, lang)],
            [L('Sharpe ratio (1 year)', 'Rasio Sharpe (1 tahun)'), k.sharpe_1y != null ? num(k.sharpe_1y, 2) : null, P.sharpe(k.sharpe_1y, lang)],
          ]
          return (
            <div className="flex flex-col gap-4">
              {items.map(([l, v, e]) => (
                <Row key={l} label={l} value={v == null ? <NA /> : <span className="inline-flex items-center gap-2"><ToneChip tone={e.tone}>{e.label}</ToneChip>{v}</span>} sub={e.sentence || undefined} />
              ))}
            </div>
          )
        }}
      </DataCard>
    </>
  )
}

const Lvl = ({ l, rate }: { l: Level; rate: number }) => {
  const L = useL()
  return (<>
    <span className="flex items-center gap-2 t-label text-navy">
      <span className={`size-2 rounded-full ${l.kind === 'support' ? 'bg-up' : 'bg-down'}`} />
      {rp(l.price, rate)}
    </span>
    <span className={`t-label-m text-right ${l.distance >= 0 ? 'text-[#048a62]' : 'text-down'}`}>{pctSigned(l.distance * 100, 1)}</span>
    <span className="t-action text-dgrey text-right whitespace-nowrap">{L(`${l.touches} touch${l.touches === 1 ? '' : 'es'}`, `${l.touches} sentuhan`)}</span>
  </>)
}

const Perf = ({ p, cols, v }: { p: string; cols: string[]; v: Record<string, number | null> }) => (
  <>
    <span className="t-label-m text-navy">{p}</span>
    {cols.map((c, i) => {
      const x = v[c]
      return <span key={c} className={`text-right ${i === 0 ? 't-label' : 't-label-m'} ${x == null ? 'text-grey' : x >= 0 ? 'text-[#048a62]' : 'text-down'}`}>
        {x == null ? '—' : pctSigned(x * 100, 1)}</span>
    })}
  </>
)

/* ---------- TradingView Lightweight Charts: line / candles, ranges, averages, support & resistance ---------- */
function PriceChart({ bars, levels, rate }: { bars: BarRow[]; levels: Level[]; rate: number }) {
  const L = useL()
  const [range, setRange] = useState<Range>('1Y')
  const [kind, setKind] = useState<'line' | 'candle'>('candle')
  const [ma, setMa] = useState(true)
  const [sr, setSr] = useState(true)
  const [tip, setTip] = useState<string | null>(null)
  const box = useRef<HTMLDivElement>(null)
  const rows = useMemo(() => bars.slice(-RANGES[range]), [bars, range])

  useEffect(() => {
    if (!box.current || rows.length < 2) return
    const chart = createChart(box.current, {
      autoSize: true,
      layout: { background: { type: ColorType.Solid, color: '#fff' }, textColor: C.dgrey, fontSize: 10, fontFamily: 'Plus Jakarta Sans', attributionLogo: true },
      grid: { vertLines: { visible: false }, horzLines: { color: '#F4F7F9' } },
      rightPriceScale: { borderVisible: false },
      timeScale: { borderVisible: false, fixLeftEdge: true, fixRightEdge: true },
      crosshair: { mode: CrosshairMode.Magnet },
      localization: { priceFormatter: (p: number) => rpShort(p, 1).replace('Rp ', '') },
      handleScroll: false, handleScale: false,
    })
    let main: ISeriesApi<SeriesType>
    if (kind === 'candle') {
      main = chart.addSeries(CandlestickSeries, { upColor: C.green, downColor: C.red, borderVisible: false, wickUpColor: C.green, wickDownColor: C.red, priceLineVisible: false })
      main.setData(rows.map((b) => ({ time: b.date, open: b.Open * rate, high: b.High * rate, low: b.Low * rate, close: b.Close * rate })))
    } else {
      main = chart.addSeries(LineSeries, { color: C.ink, lineWidth: 2, priceLineVisible: false })
      main.setData(rows.map((b) => ({ time: b.date, value: b.Close * rate })))
    }
    if (ma) {
      for (const [k, color] of [['sma50', C.blue], ['sma200', C.amber]] as const) {
        const s = chart.addSeries(LineSeries, { color, lineWidth: 1, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false })
        s.setData(rows.filter((b) => b[k] != null).map((b) => ({ time: b.date, value: b[k]! * rate })))
      }
    }
    if (sr) for (const l of levels) {
      main.createPriceLine({ price: l.price * rate, color: l.kind === 'support' ? C.green : C.red, lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: false, title: '' })
    }
    chart.timeScale().fitContent()
    chart.subscribeCrosshairMove((p) => {
      const d = p.seriesData.get(main) as any
      const v = d?.close ?? d?.value
      setTip(v != null && p.time ? `${dateShort(String(p.time))} · Rp ${num(v)}` : null)
    })
    return () => chart.remove()
  }, [rows, kind, ma, sr, levels, rate])

  return (
    <>
      <div className="flex items-center justify-between gap-2">
        <Pills small label={L('Chart type', 'Jenis grafik')} value={kind} onChange={setKind} options={[{ key: 'candle', label: L('Candles', 'Candle') }, { key: 'line', label: L('Line', 'Garis') }]} />
        <span className="t-action-b text-navy">{tip ?? L('Tap the chart for prices', 'Ketuk grafik untuk harga')}</span>
      </div>
      <div ref={box} className="h-[240px] w-full mt-3" />
      <div className="flex justify-between mt-3">
        {(Object.keys(RANGES) as Range[]).map((r) => (
          <button key={r} type="button" onClick={() => setRange(r)} aria-pressed={r === range}
            className={`t-label rounded-full px-3 pt-1 pb-0.5 border-0 cursor-pointer ${r === range ? 'bg-chip text-navy' : 'bg-transparent text-grey'}`}>{r}</button>
        ))}
      </div>
      <div className="flex gap-2 mt-3 flex-wrap">
        <Toggle on={ma} set={setMa} label={L('Averages 50 / 200 days', 'Rata-rata 50 / 200 hari')} dots={[C.blue, C.amber]} />
        <Toggle on={sr} set={setSr} label="Support / resistance" dots={[C.green, C.red]} />
      </div>
    </>
  )
}

const Toggle = ({ on, set, label, dots }: { on: boolean; set: (b: boolean) => void; label: string; dots: string[] }) => (
  <button type="button" aria-pressed={on} onClick={() => set(!on)}
    className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 t-action-b border cursor-pointer ${on ? 'border-purple bg-lavender text-purple' : 'border-grey2 bg-white text-dgrey'}`}>
    {dots.map((c) => <span key={c} className="size-2 rounded-full" style={{ background: c, opacity: on ? 1 : 0.4 }} />)}{label}
  </button>
)

/* ---------- RSI, MACD and the signals list (last 6 months) ---------- */
function Momentum({ d }: { d: any }) {
  const L = useL()
  const rows: BarRow[] = (d.bars?.items ?? []).slice(-126)
  const signals = d.signals?.items ?? []
  const rsi = d.snapshot?.value?.rsi14
  const lbl = (s: string) => dateShort(s).replace(/ \d{4}$/, '')
  return (
    <>
      <div className="flex justify-between"><span className="t-label text-navy">{L('RSI (14 days)', 'RSI (14 hari)')}</span><span className="t-link text-navy">{rsi != null ? num(rsi, 1) : '—'}</span></div>
      <ChartBox h={120}>
        <LineChart data={rows} margin={{ top: 6, right: 4, left: -24, bottom: 0 }}>
          <ReferenceArea y1={70} y2={100} fill={C.red} fillOpacity={0.06} />
          <ReferenceArea y1={0} y2={30} fill={C.green} fillOpacity={0.08} />
          <ReferenceLine y={70} stroke={C.red} strokeDasharray="3 3" />
          <ReferenceLine y={30} stroke={C.green} strokeDasharray="3 3" />
          <XAxis dataKey="date" tick={axisTick} tickFormatter={lbl} minTickGap={50} axisLine={false} tickLine={false} />
          <YAxis domain={[0, 100]} ticks={[30, 70]} tick={axisTick} axisLine={false} tickLine={false} />
          <TapTip fmt={(v) => num(v, 1)} />
          <Line isAnimationActive={false} dataKey="rsi14" name="RSI" stroke={C.purple} strokeWidth={1.5} dot={false} />
        </LineChart>
      </ChartBox>
      <p className="t-action text-dgrey mt-1 mb-0">{L('Above 70 = rose fast recently ("overbought"); below 30 = fell fast ("oversold").', 'Di atas 70 = naik cepat belakangan ("overbought"); di bawah 30 = turun cepat ("oversold").')}</p>

      <div className="t-label text-navy mt-4">MACD</div>
      <ChartBox h={110}>
        <BarChart data={rows} margin={{ top: 6, right: 4, left: -24, bottom: 0 }}>
          <XAxis dataKey="date" tick={axisTick} tickFormatter={lbl} minTickGap={50} axisLine={false} tickLine={false} />
          <YAxis tick={axisTick} axisLine={false} tickLine={false} />
          <TapTip fmt={(v) => num(v, 2)} />
          <Bar isAnimationActive={false} dataKey="hist" name="MACD histogram">
            {rows.map((r, i) => <Cell key={i} fill={(r.hist ?? 0) >= 0 ? C.green : C.red} />)}
          </Bar>
        </BarChart>
      </ChartBox>

      <div className="t-label text-navy mt-4">{L('Signals (facts, not advice)', 'Sinyal (fakta, bukan saran)')}</div>
      <ul className="list-none m-0 p-0 mt-2 flex flex-col gap-2">
        {signals.map((s: any, i: number) => (
          <li key={i} className="flex gap-2 t-label-m text-navy">
            <span className={`size-2 rounded-full mt-1.5 shrink-0 ${s.tone === 'positive' ? 'bg-up' : s.tone === 'negative' ? 'bg-down' : 'bg-grey'}`} />
            <span>{s.fact} <span className="text-dgrey t-action">· {dateShort(s.date)}</span></span>
          </li>
        ))}
        {!signals.length && <li className="t-label-m text-dgrey">{L('No new signals in the last 6 months.', 'Tidak ada sinyal baru dalam 6 bulan terakhir.')}</li>}

      </ul>
    </>
  )
}
