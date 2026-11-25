import { useState } from 'react'
import { Bar, BarChart, Cell, Line, LineChart, ReferenceLine, XAxis, YAxis } from 'recharts'
import { ep, useData, useSettings } from '../lib/data'
import { dateShort, num, pct, rp, rpS, rpShort } from '../lib/format'
import { latest, table, type FinData } from '../lib/fin'
import { useT } from '../lib/i18n'
import { C, ChartBox, Legend, TapTip, axisTick } from '../components/charts'
import { Badge, DataCard, NA, Pills, Row, Val } from '../components/ui'

type Period = 'quarterly' | 'annual'
const shortRp = (rate: number) => (v: number) => rpShort(v * rate, 0).replace('Rp ', '')

export function FinancialsTab({ rate, onFullStatement }: { rate: number; onFullStatement: (p: Period) => void }) {
  const t = useT()
  const [period, setPeriod] = useState<Period>('quarterly')
  const n = period === 'quarterly' ? 8 : 5
  const inc = useData<FinData>((tk) => ep.financials(tk, period, 'income'))
  const cf = useData<FinData>((tk) => ep.financials(tk, period, 'cashflow'))
  const bal = useData<FinData>((tk) => ep.financials(tk, period, 'balance'))
  const ern = useData<any>(ep.earnings)
  const money = (v: number) => rpS(v, rate)

  return (
    <>
      <Pills label="Period" value={period} onChange={setPeriod}
        options={[{ key: 'quarterly', label: t('quarterly') }, { key: 'annual', label: t('annual') }]} />

      <DataCard q={inc} title={t('rev_profit')} info="revenue" h={200}>
        {(d) => {
          const rows = table(d, ['revenue', 'net_income'], n)
          const nm = latest(d, 'net_margin')
          return !rows.length ? <NA reason="No statements" /> : (
            <>
              <ChartBox h={190}>
                <BarChart data={rows} margin={{ top: 8, right: 0, left: -4, bottom: 0 }} barGap={2}>
                  <XAxis dataKey="label" tick={axisTick} axisLine={false} tickLine={false} interval={0} tickFormatter={(l) => String(l).replace(' FY', "'")} />
                  <YAxis tick={axisTick} axisLine={false} tickLine={false} width={48} tickFormatter={shortRp(rate)} />
                  <ReferenceLine y={0} stroke={C.grey2} />
                  <TapTip fmt={money} />
                  <Bar isAnimationActive={false} dataKey="revenue" name="Revenue" fill={C.purpleLight} radius={[3, 3, 0, 0]} />
                  <Bar isAnimationActive={false} dataKey="net_income" name="Net income" fill={C.purple} radius={[3, 3, 0, 0]} />
                </BarChart>
              </ChartBox>
              <Legend items={[['Revenue', C.purpleLight], ['Net income', C.purple]]} />
              {nm != null && <p className="t-label-m text-navy mt-3 mb-0">Latest net margin: <b>{pct(nm)}</b> of revenue kept as profit.</p>}
              <p className="t-action text-dgrey mt-1 mb-0">Tap a bar to see exact values. Source: {d.rows[0]?.license_tag === 'COMMERCIAL_OK' ? 'SEC filings' : 'company filings'} <Badge tag={d.rows[0]?.license_tag} /></p>
            </>
          )
        }}
      </DataCard>

      <DataCard q={inc} title={t('margins')} info="margins" defaultOpen={false}>
        {(d) => {
          const rows = table(d, ['gross_margin', 'operating_margin', 'net_margin'], n)
          return (
            <>
              <ChartBox h={170}>
                <LineChart data={rows} margin={{ top: 8, right: 6, left: -12, bottom: 0 }}>
                  <XAxis dataKey="label" tick={axisTick} axisLine={false} tickLine={false} interval={0} tickFormatter={(l) => String(l).replace(' FY', "'")} />
                  <YAxis tick={axisTick} axisLine={false} tickLine={false} width={40} tickFormatter={(v) => `${Math.round(v * 100)}%`} />
                  <TapTip fmt={(v) => pct(v, 1)} />
                  <Line isAnimationActive={false} dataKey="gross_margin" name="Gross" stroke={C.purpleLight} strokeWidth={2} dot={{ r: 2 }} connectNulls />
                  <Line isAnimationActive={false} dataKey="operating_margin" name="Operating" stroke={C.blue} strokeWidth={2} dot={{ r: 2 }} connectNulls />
                  <Line isAnimationActive={false} dataKey="net_margin" name="Net" stroke={C.purple} strokeWidth={2} dot={{ r: 2 }} connectNulls />
                </LineChart>
              </ChartBox>
              <Legend items={[['Gross', C.purpleLight], ['Operating', C.blue], ['Net', C.purple]]} />
              {d.not_available?.gross_margin && <p className="t-action text-grey mt-2 mb-0">N/A · {d.not_available.gross_margin}</p>}
            </>
          )
        }}
      </DataCard>

      <DataCard q={cf} title={t('cash_flow')} info="fcf" defaultOpen={false}>
        {(d) => {
          const rows = table(d, ['operating_cash_flow', 'capex', 'fcf'], n).map((r) => ({ ...r, capex: r.capex == null ? null : -Math.abs(r.capex) }))
          return (
            <>
              <ChartBox h={180}>
                <BarChart data={rows} margin={{ top: 8, right: 0, left: -4, bottom: 0 }} barGap={1}>
                  <XAxis dataKey="label" tick={axisTick} axisLine={false} tickLine={false} interval={0} tickFormatter={(l) => String(l).replace(' FY', "'")} />
                  <YAxis tick={axisTick} axisLine={false} tickLine={false} width={48} tickFormatter={shortRp(rate)} />
                  <ReferenceLine y={0} stroke={C.grey} />
                  <TapTip fmt={money} />
                  <Bar isAnimationActive={false} dataKey="operating_cash_flow" name="Operating cash flow" fill={C.blue} radius={[3, 3, 0, 0]} />
                  <Bar isAnimationActive={false} dataKey="capex" name="Capex" fill={C.grey} />
                  <Bar isAnimationActive={false} dataKey="fcf" name="Free cash flow" fill={C.purple} radius={[3, 3, 0, 0]} />
                </BarChart>
              </ChartBox>
              <Legend items={[['Operating cash flow', C.blue], ['Capex (spent)', C.grey], ['Free cash flow', C.purple]]} />
            </>
          )
        }}
      </DataCard>

      <DataCard q={bal} title={t('cash_debt')} info="net_debt" defaultOpen={false}>
        {(d) => {
          const rows = table(d, ['cash', 'total_debt'], n)
          const nd = latest(d, 'net_debt')
          return (
            <>
              <ChartBox h={170}>
                <BarChart data={rows} margin={{ top: 8, right: 0, left: -4, bottom: 0 }} barGap={2}>
                  <XAxis dataKey="label" tick={axisTick} axisLine={false} tickLine={false} interval={0} tickFormatter={(l) => String(l).replace(' FY', "'")} />
                  <YAxis tick={axisTick} axisLine={false} tickLine={false} width={48} tickFormatter={shortRp(rate)} />
                  <TapTip fmt={money} />
                  <Bar isAnimationActive={false} dataKey="cash" name="Cash" fill={C.green} radius={[3, 3, 0, 0]} />
                  <Bar isAnimationActive={false} dataKey="total_debt" name="Total debt" fill={C.red} radius={[3, 3, 0, 0]} />
                </BarChart>
              </ChartBox>
              <Legend items={[['Cash', C.green], ['Total debt', C.red]]} />
              <div className="mt-3"><Row label="Net debt (latest)" value={nd == null ? <NA reason={d.not_available?.net_debt} /> : rpS(nd, rate)} /></div>
            </>
          )
        }}
      </DataCard>

      <DataCard q={ern} title={t('earnings')} info="eps_surprise" defaultOpen={false}>
        {(d) => <Earnings d={d} rate={rate} />}
      </DataCard>

      <button type="button" onClick={() => onFullStatement(period)}
        className="w-full bg-white rounded-2xl shadow-card p-4 flex items-center justify-between border-0 cursor-pointer">
        <span className="t-link text-navy">{t('full_statement')}</span>
        <span className="size-7 rounded-full bg-lavender grid place-items-center text-purple font-bold">›</span>
      </button>
    </>
  )
}

function Earnings({ d, rate }: { d: any; rate: number }) {
  const up = d.upcoming?.value
  const hist = (d.history?.items ?? []).filter((h: any) => h.eps_reported != null).slice(-8)
  const br = d.beat_rate_8?.value
  return (
    <>
      <div className="rounded-xl bg-lgrey p-3">
        <div className="t-label text-navy">Next earnings <Badge tag={d.upcoming?.license_tag} /></div>
        {up ? (
          <div className="flex flex-col gap-2 mt-2">
            <Row label="Date" value={`${dateShort(up.date)}${up.timing ? ` · ${up.timing}` : ''}`} />
            {up.eps_estimate != null && <Row label="Expected EPS" value={rp(up.eps_estimate, rate)} />}
            {up.revenue_estimate != null && <Row label="Expected revenue" value={rpS(up.revenue_estimate, rate)} />}
            {up.analysts != null && <Row label="Analysts covering" value={num(up.analysts)} />}
          </div>
        ) : <div className="mt-1"><NA reason={d.upcoming?.na_reason ?? 'No date announced yet'} /></div>}
      </div>
      {hist.length ? (
        <div className="mt-4">
          <div className="t-label text-navy">EPS: actual vs expected</div>
          <ChartBox h={170}>
            <BarChart data={hist.map((h: any) => ({ ...h, exp: h.eps_estimate != null ? h.eps_estimate * rate : null, act: h.eps_reported * rate }))}
              margin={{ top: 8, right: 0, left: -4, bottom: 0 }} barGap={1}>
              <XAxis dataKey="quarter" tick={axisTick} axisLine={false} tickLine={false} interval={0} tickFormatter={(l) => String(l ?? '').replace(' FY', "'")} />
              <YAxis tick={axisTick} axisLine={false} tickLine={false} width={48} tickFormatter={(v) => rpShort(v, 0).replace('Rp ', '')} />
              <ReferenceLine y={0} stroke={C.grey} />
              <TapTip fmt={(v) => `Rp ${num(v)}`} />
              <Bar isAnimationActive={false} dataKey="exp" name="Expected" fill={C.grey2} radius={[3, 3, 0, 0]} />
              <Bar isAnimationActive={false} dataKey="act" name="Actual" radius={[3, 3, 0, 0]}>
                {hist.map((h: any, i: number) => <Cell key={i} fill={h.result === 'miss' ? C.red : h.result === 'beat' ? C.green : C.navy} />)}
              </Bar>
            </BarChart>
          </ChartBox>
          <Legend items={[['Expected', C.grey2], ['Beat', C.green], ['Miss', C.red]]} />
        </div>
      ) : <div className="mt-3"><NA reason={d.history?.na_reason ?? 'No earnings history'} /></div>}
      <div className="flex flex-col gap-3 mt-4">
        <Row label="Beat rate (last 8 quarters)" value={br ? `${br.beats} of ${br.quarters}` : <NA reason={d.beat_rate_8?.na_reason} />} />
        <Row label="Typical move after earnings" value={<Val v={d.typical_move} f={(x) => `±${pct(x, 1)}`} />} />
      </div>
    </>
  )
}

/* ---------- Full statement page: Income / Balance / Cash flow, sideways-scrolling table ---------- */
export function StatementPage({ period: p0, rate, onClose }: { period: Period; rate: number; onClose: () => void }) {
  const t = useT()
  const { ticker } = useSettings()
  const [period, setPeriod] = useState<Period>(p0)
  const [st, setSt] = useState<'income' | 'balance' | 'cashflow'>('income')
  const q = useData<FinData>((tk) => ep.financials(tk, period, st))
  const fmt = (v: number | null, unit: string) => v == null ? '—'
    : unit === 'USD' ? rpShort(v * rate, 1).replace('Rp ', '')
      : unit === 'ratio' ? pct(v, 1) : unit === 'USD/shares' ? num(v * rate) : unit === 'shares' ? `${num(v / 1e6)}M` : num(v, 2)
  const d = q.data
  const periods = d ? [...d.periods].sort((a, b) => b.period_end.localeCompare(a.period_end)) : []
  const fields = d ? [...new Map(d.rows.map((r) => [r.field, r])).values()] : []
  const cell = (f: string, end: string) => d!.rows.find((r) => r.field === f && r.period_end === end)

  return (
    <div className="fixed inset-0 z-30 bg-white flex flex-col" role="dialog" aria-label={t('full_statement')}>
      <div className="flex items-center gap-3 px-6 h-[58px] shrink-0">
        <button type="button" onClick={onClose} aria-label="Back" className="size-6 grid place-items-center bg-transparent border-0 p-0 cursor-pointer">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none"><path d="M20 12H5M11 5l-7 7 7 7" stroke="#082F57" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" /></svg>
        </button>
        <span className="t-link text-navy">{ticker} · {t('full_statement').replace('See ', '')}</span>
      </div>
      <div className="px-6 flex flex-col gap-3 shrink-0">
        <Pills label="Statement" value={st} onChange={setSt} options={[{ key: 'income', label: 'Income' }, { key: 'balance', label: 'Balance' }, { key: 'cashflow', label: 'Cash flow' }]} />
        <Pills small label="Period" value={period} onChange={setPeriod} options={[{ key: 'quarterly', label: t('quarterly') }, { key: 'annual', label: t('annual') }]} />
        <p className="t-action text-dgrey m-0">Amounts in Rp (K, M, B, T). <span className="text-purple font-bold">•</span> = calculated by us.</p>
      </div>
      <div className="flex-1 overflow-auto mt-3 border-t border-grey2">
        {q.loading ? <div className="p-6 t-label-m text-grey">Loading…</div> : q.error || !d ? <div className="p-6 t-label-m text-down">{q.error}</div> : (
          <table className="border-collapse text-[12px] leading-4">
            <thead>
              <tr>
                <th className="sticky top-0 left-0 z-20 bg-lgrey text-left px-3 py-2 t-action-b text-navy min-w-[150px]">Item</th>
                {periods.map((p) => <th key={p.period_end} className="sticky top-0 z-10 bg-lgrey px-3 py-2 t-action-b text-navy whitespace-nowrap text-right">{p.label}</th>)}
              </tr>
            </thead>
            <tbody>
              {fields.map((f) => (
                <tr key={f.field} className="border-b border-grey2">
                  <td className="sticky left-0 z-10 bg-white px-3 py-2 font-medium text-navy max-w-[160px]">{f.label}</td>
                  {periods.map((p) => {
                    const c = cell(f.field, p.period_end)
                    return <td key={p.period_end} className="px-3 py-2 text-right font-bold text-navy whitespace-nowrap">
                      {fmt(c?.value ?? null, f.unit)}{c?.derived && <span className="text-purple"> •</span>}</td>
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
