import { Bar, BarChart, Line, LineChart, ReferenceArea, ReferenceLine, XAxis, YAxis } from 'recharts'
import { ep, useData, useSettings, type V } from '../lib/data'
import { dateShort, num, pct, pctSigned, rp, rpS } from '../lib/format'
import { useT } from '../lib/i18n'
import * as P from '../lib/plain'
import { C, ChartBox, TapTip, axisTick } from '../components/charts'
import { DataCard, Empty, NA, Row, ToneChip, Val } from '../components/ui'

const x2 = (v: number) => `${num(v, 2)}x`

export function FundamentalsTab({ rate, priceUsd }: { rate: number; priceUsd: number | null }) {
  const t = useT()
  const { lang } = useSettings()
  const sum = useData<any>(ep.summary)
  const rat = useData<any>(ep.ratios)
  const val = useData<any>(ep.valuation)
  const div = useData<any>(ep.dividends)
  const prof = useData<any>(ep.profile)
  const isFin = !!prof.data?.is_financial_company

  return (
    <>
      {/* Valuation: now vs its own 5-year history vs peers */}
      <DataCard q={rat} title={t('valuation')} info="valuation_history" h={260}>
        {(r) => {
          const hs = val.data?.history_stats ?? {}
          const pm = val.data?.peer_medians?.value ?? {}
          const cmp = (k: string) => {
            const med = hs[k]?.value?.median, peer = pm[k]
            const parts = [med != null && `5-yr median ${x2(med)}`, peer != null && `peers ${x2(peer)}`].filter(Boolean)
            return parts.length ? parts.join(' · ') : undefined
          }
          const pe = hs.pe?.value
          const hist = (val.data?.history_weekly?.items ?? []).filter((h: any) => h.pe != null)
          return (
            <>
              <div className="flex flex-col gap-4">
                <Row label="Share price" value={<Val v={sum.data?.header?.price} f={(x) => rp(x, rate)} />} />
                <Row label="Market cap" value={<Val v={sum.data?.header?.market_cap} f={(x) => rpS(x, rate)} />} />
                <Row label="P/E" value={<Val v={r.pe} f={x2} />} sub={cmp('pe')} />
                <Row label="P/S" value={<Val v={r.ps} f={x2} />} sub={cmp('ps')} />
                <Row label="P/B" value={<Val v={r.pb} f={x2} />} />
                <Row label="EV/EBITDA" value={<Val v={r.ev_ebitda} f={x2} />} sub={cmp('ev_ebitda')} />
                <Row label="FCF yield" value={<Val v={r.fcf_yield} f={(x) => pct(x)} />} />
              </div>
              {hist.length > 10 && pe && (
                <div className="mt-5">
                  <div className="t-label text-navy">P/E over 5 years</div>
                  <ChartBox h={160}>
                    <LineChart data={hist} margin={{ top: 8, right: 4, left: -18, bottom: 0 }}>
                      <ReferenceArea y1={Math.max(pe.low, pe.median - pe.std)} y2={Math.min(pe.high, pe.median + pe.std)} fill={C.purple} fillOpacity={0.07} />
                      <ReferenceLine y={pe.median} stroke={C.purple} strokeDasharray="4 3" label={{ value: 'median', fill: C.purple, fontSize: 10, position: 'insideTopLeft' }} />
                      <XAxis dataKey="date" tick={axisTick} tickFormatter={(d) => String(d).slice(0, 4)} interval="preserveStartEnd" minTickGap={40} axisLine={false} tickLine={false} />
                      <YAxis tick={axisTick} axisLine={false} tickLine={false} width={44} />
                      <TapTip fmt={(v) => x2(v)} />
                      <Line isAnimationActive={false} dataKey="pe" name="P/E" stroke={C.navy} strokeWidth={2} dot={false} />
                    </LineChart>
                  </ChartBox>
                  <p className="t-label-m text-navy mt-2 mb-0">
                    P/E is higher than {num(pe.percentile * 100)}% of the last 5 years.
                  </p>
                </div>
              )}
            </>
          )
        }}
      </DataCard>

      {/* Fair value estimate */}
      <DataCard q={val} title={t('fair_value')} info="dcf" defaultOpen h={220}>
        {(d) => <FairValue d={d} rate={rate} priceUsd={priceUsd} />}
      </DataCard>

      {/* Profitability */}
      <DataCard q={rat} title={t('profitability')} info="roe" defaultOpen={false}>
        {(r) => (
          <>
            <div className="flex flex-col gap-4">
              {([['ROE', 'roe', 0.15, 0.08], ['ROA', 'roa', 0.08, 0.03], ['ROIC', 'roic', 0.12, 0.06],
                ['Gross margin (TTM)', 'gross_margin', 0.4, 0.2], ['Operating margin (TTM)', 'operating_margin', 0.15, 0.05],
                ['Net margin (TTM)', 'net_margin', 0.15, 0.05]] as const).map(([l, k, g, o]) => (
                <Row key={k} label={l} value={<span className="inline-flex items-center gap-2">
                  {r[k]?.value != null && <ToneChip tone={P.simpleLevel(r[k].value, g, o, lang).tone}>{P.simpleLevel(r[k].value, g, o, lang).label}</ToneChip>}
                  <Val v={r[k]} f={(x) => pct(x)} /></span>} />
              ))}
            </div>
            <div className="mt-5 rounded-xl bg-lgrey p-3">
              <div className="t-label text-navy">Where ROE comes from</div>
              <div className="flex flex-col gap-2 mt-2">
                <Row label="Net margin" value={<Val v={r.net_margin} f={(x) => pct(x)} />} />
                <Row label="× Asset turnover" value={<Val v={r.asset_turnover} f={x2} />} />
                <Row label="× Leverage" value={<Val v={r.equity_multiplier} f={x2} />} />
                <Row label="= ROE" value={<Val v={r.roe} f={(x) => pct(x)} />} />
              </div>
            </div>
          </>
        )}
      </DataCard>

      {/* Growth */}
      <DataCard q={rat} title={t('growth')} info="cagr" defaultOpen={false}>
        {(r) => (
          <div className="flex flex-col gap-4">
            {([['Revenue vs last year', 'revenue_yoy'], ['EPS vs last year', 'eps_yoy'],
              ['Revenue, 3 yrs (per year)', 'revenue_cagr_3y'], ['Revenue, 5 yrs (per year)', 'revenue_cagr_5y'],
              ['EPS, 3 yrs (per year)', 'eps_cagr_3y'], ['EPS, 5 yrs (per year)', 'eps_cagr_5y']] as const).map(([l, k]) => (
              <Row key={k} label={l} value={<Val v={r[k]} f={(x) => <span className={x >= 0 ? 'text-[#048a62]' : 'text-down'}>{pctSigned(x * 100)}</span>} />} />
            ))}
          </div>
        )}
      </DataCard>

      {/* Financial health */}
      <DataCard q={rat} title={t('health')} info="piotroski" defaultOpen={false}>
        {(r) => <Health r={r} rate={rate} isFin={isFin} />}
      </DataCard>

      {/* Dividends */}
      <DataCard q={div} title={t('dividends')} info="dividend_yield" defaultOpen={false}>
        {(d) => !d.pays_dividend ? <Empty>This company does not pay a dividend. {d.message ?? ''}</Empty> : <Dividends d={d} rate={rate} />}
      </DataCard>
    </>
  )
}

/* ---------- Fair value: today's price vs Graham number, DCF scenarios and analysts' mean target ---------- */
function FairValue({ d, rate, priceUsd }: { d: any; rate: number; priceUsd: number | null }) {
  const t = useT()
  const sc = d.dcf?.scenarios ?? {}
  const items: { label: string; v: V | undefined; color: string }[] = [
    { label: 'Graham number', v: d.graham_number, color: C.blue },
    { label: 'DCF · bear case', v: sc.Bear, color: C.red },
    { label: 'DCF · base case', v: sc.Base, color: C.purple },
    { label: 'DCF · bull case', v: sc.Bull, color: C.green },
    { label: "Analysts' mean target", v: d.analyst_targets ? { ...d.analyst_targets, value: d.analyst_targets.value?.mean ?? null } : undefined, color: C.amber },
  ]
  if (priceUsd == null) return <NA reason="Price not available" />
  const vals = items.map((i) => (i.v?.value as number | null) ?? null).filter((x): x is number => x != null && x > 0)
  const max = Math.max(priceUsd, ...vals) * 1.08
  const pos = (x: number) => `${Math.min(100, (x / max) * 100)}%`
  return (
    <>
      <div className="rounded-xl bg-down-bg/60 px-3 py-2 t-label text-navy text-center">{t('estimate')}</div>
      <div className="flex flex-col gap-4 mt-4">
        <FvRow label="Today's price" value={rp(priceUsd, rate)} pos={pos(priceUsd)} color={C.ink} bold />
        {items.map((i) => {
          const x = i.v?.value as number | null | undefined
          return x != null && x > 0 ? (
            <FvRow key={i.label} label={i.label} value={rp(x, rate)} pos={pos(x)} color={i.color}
              diff={pctSigned((x / priceUsd - 1) * 100, 0)} up={x >= priceUsd} />
          ) : (
            <div key={i.label} className="flex justify-between gap-3"><span className="t-label-m text-navy">{i.label}</span><NA reason={i.v?.na_reason ?? i.v?.note ?? d.dcf?.na_reason} /></div>
          )
        })}
      </div>
      {d.dcf?.assumptions && (
        <p className="t-action text-dgrey mt-4 mb-0">
          DCF assumptions: cash flow grows {pct(d.dcf.assumptions.growth, 1)} a year ({d.dcf.assumptions.growth_source}),
          discount rate {pct(d.dcf.assumptions.discount_rate, 0)}, long-term growth {pct(d.dcf.assumptions.terminal_growth, 1)}.
          Bear / bull change growth down / up.
        </p>
      )}
    </>
  )
}

function FvRow({ label, value, pos, color, diff, up, bold }: { label: string; value: string; pos: string; color: string; diff?: string; up?: boolean; bold?: boolean }) {
  return (
    <div>
      <div className="flex justify-between gap-2">
        <span className={`${bold ? 't-label' : 't-label-m'} text-navy`}>{label}</span>
        <span className="t-label text-navy whitespace-nowrap">{value}
          {diff && <span className={`ml-1.5 t-action-b ${up ? 'text-[#048a62]' : 'text-down'}`}>{diff}</span>}</span>
      </div>
      <div className="relative h-2 rounded-full bg-grey2 mt-1.5">
        <div className="absolute left-0 top-0 h-2 rounded-full" style={{ width: pos, background: color, opacity: bold ? 1 : 0.85 }} />
      </div>
    </div>
  )
}

/* ---------- Health: Piotroski checklist, Altman Z, debt & cash ---------- */
function Health({ r, rate, isFin }: { r: any; rate: number; isFin: boolean }) {
  const pio = r.piotroski
  const alt = r.altman_z
  const z = alt?.value as number | null
  return (
    <>
      <div className="flex items-center justify-between">
        <span className="t-label text-navy">Piotroski score</span>
        <span className="t-link text-navy">{pio?.value != null ? `${pio.value} / ${pio.tests_run}` : 'N/A'}</span>
      </div>
      {pio?.checks?.length ? (
        <ul className="list-none m-0 p-0 mt-2 flex flex-col gap-2.5">
          {pio.checks.map((c: any) => (
            <li key={c.name} className="flex gap-2">
              <span className={`size-5 rounded-full grid place-items-center shrink-0 text-[11px] font-bold ${c.passed == null ? 'bg-lgrey text-grey' : c.passed ? 'bg-up-bg text-up' : 'bg-down-bg text-down'}`}>
                {c.passed == null ? '–' : c.passed ? '✓' : '✗'}</span>
              <span>
                <span className="t-label-m text-navy block">{c.name}</span>
                <span className="t-action text-dgrey block">{c.explanation}{c.detail ? ` (${c.detail})` : ''}</span>
              </span>
            </li>
          ))}
        </ul>
      ) : <div className="mt-2"><NA reason={pio?.na_reason} /></div>}

      <div className="mt-5 flex items-center justify-between">
        <span className="t-label text-navy">Altman Z-score</span>
        <span className="t-link text-navy">{z != null ? `${num(z, 2)} · ${alt.zone}` : ''}</span>
      </div>
      {z != null ? (
        <div className="mt-2">
          <div className="relative flex h-2.5 rounded-full overflow-hidden">
            <div className="bg-down" style={{ width: `${(1.81 / 6) * 100}%` }} />
            <div className="bg-amber-400" style={{ width: `${((2.99 - 1.81) / 6) * 100}%` }} />
            <div className="bg-up flex-1" />
          </div>
          <div className="relative h-4">
            <span className="absolute -top-1 -translate-x-1/2 text-navy text-xs" style={{ left: `${Math.min(z, 6) / 6 * 100}%` }}>▲</span>
          </div>
          <div className="flex justify-between t-action text-dgrey"><span>Distress</span><span>Grey</span><span>Safe</span></div>
          <p className="t-action text-dgrey mt-1 mb-0">Scale capped at 6.</p>
        </div>
      ) : <div className="mt-1"><NA reason={alt?.na_reason ?? (isFin ? 'Not meaningful for banks' : undefined)} /></div>}

      <div className="mt-5 t-label text-navy">Debt & cash</div>
      <div className="flex flex-col gap-3 mt-2">
        <Row label="Net debt" value={<Val v={r.net_debt} f={(x) => rpS(x, rate)} />} />
        <Row label="Debt to equity" value={<Val v={r.debt_to_equity} f={x2} />} />
        <Row label="Current ratio" value={<Val v={r.current_ratio} f={x2} />} />
        <Row label="Interest coverage" value={<Val v={r.interest_coverage} f={x2} />} />
      </div>
    </>
  )
}

/* ---------- Dividends ---------- */
function Dividends({ d, rate }: { d: any; rate: number }) {
  const thisYear = new Date().getFullYear()
  const bars = Object.entries((d.annual_dps?.value ?? {}) as Record<string, number>)
    .filter(([y]) => Number(y) < thisYear).slice(-8).map(([y, v]) => ({ y, v: v * rate }))
  return (
    <>
      <div className="flex flex-col gap-4">
        <Row label="Dividend yield" value={<Val v={d.yield_ttm} f={(x) => pct(x)} />} />
        <Row label="Payout ratio" value={<Val v={d.payout_ratio} f={(x) => pct(x, 0)} />} />
        <Row label="Years of raises" value={<Val v={d.growth_streak_years} f={(x) => `${x} years`} />} />
        <Row label="Next ex-dividend date" value={<Val v={d.next_ex_dividend_date} f={(x) => dateShort(x)} />} />
      </div>
      {bars.length > 1 && (
        <div className="mt-5">
          <div className="t-label text-navy">Dividend per share by year</div>
          <ChartBox h={160}>
            <BarChart data={bars} margin={{ top: 8, right: 0, left: -6, bottom: 0 }}>
              <XAxis dataKey="y" tick={axisTick} axisLine={false} tickLine={false} />
              <YAxis tick={axisTick} axisLine={false} tickLine={false} width={50} tickFormatter={(v) => `${num(v / 1000)}K`} />
              <TapTip fmt={(v) => `Rp ${num(v)}`} />
              <Bar isAnimationActive={false} dataKey="v" name="Dividend" fill={C.purple} radius={[4, 4, 0, 0]} />
            </BarChart>
          </ChartBox>
        </div>
      )}
    </>
  )
}

