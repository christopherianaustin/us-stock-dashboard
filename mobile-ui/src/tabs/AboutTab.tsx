import { Bar, BarChart, Cell, Pie, PieChart, ReferenceLine, XAxis, YAxis } from 'recharts'
import { ep, useData, useSettings } from '../lib/data'
import { dateShort, num, pct, rpShort } from '../lib/format'
import { useL, useT } from '../lib/i18n'
import { AIInsight } from '../components/AIInsight'
import { CompanyCard } from '../components/Cards'
import { C, ChartBox, Legend, TapTip, axisTick } from '../components/charts'
import { DataCard, Empty, ErrorLine, NA, Row, Skeleton, Val } from '../components/ui'

const FEATURED = [['All Stocks', 'Top 100', 'Sports', 'Social Media'], ['Eco Friendly', 'Visionary', 'Tech Giants', 'Lifestyle']]
const chip = 't-label-m text-navy bg-white border border-grey2 rounded-full px-4 py-1 whitespace-nowrap cursor-pointer'

export function AboutTab({ rate, onToast }: { rate: number; onToast: (m: string) => void }) {
  const t = useT()
  const L = useL()
  const s = useSettings()
  const prof = useData<any>(ep.profile)
  const own = useData<any>(ep.ownership)

  return (
    <>
      {!prof.loading && prof.data && <AIInsight tab="company_profile" standalone />}
      {prof.loading ? <Skeleton h={300} /> : prof.error || !prof.data ? (
        <section className="bg-white rounded-2xl shadow-card p-4"><ErrorLine onRetry={prof.retry} detail={prof.error} kind={prof.errKind} /></section>
      ) : (() => {
        const p = prof.data
        const v = (k: string) => p[k]
        const site = p.website?.value as string | null
        return (
          <CompanyCard legalName={p.name?.value ?? s.ticker} ticker={s.ticker} description={p.description?.value ?? p.description?.na_reason ?? L('No description available.', 'Deskripsi tidak tersedia.')}
            rows={[
              { label: 'CEO', value: <Val v={v('ceo')} f={(x) => String(x).replace(/^(Mr\.|Ms\.|Mrs\.|Dr\.) /, '')} /> },
              { label: L('Industry', 'Industri'), value: <Val v={v('industry')} f={String} /> },
              { label: L('Sector', 'Sektor'), value: <Val v={v('sector')} f={String} /> },
              { label: L('Number of employees', 'Jumlah karyawan'), value: <Val v={v('employees')} f={(x) => num(x)} /> },
              { label: L('Headquarters', 'Kantor pusat'), value: <Val v={v('headquarters')} f={String} /> },
              { label: 'Website', value: site ? <a href={site} target="_blank" rel="noreferrer noopener" className="text-purple no-underline">{site.replace(/^https?:\/\/(www\.)?/, '').replace(/\/$/, '')}</a> : <Val v={v('website')} f={String} /> },
              { label: L('Exchange', 'Bursa'), value: <Val v={v('exchange')} f={String} /> },
              { label: L('Fiscal year end', 'Akhir tahun fiskal'), value: <Val v={v('fiscal_year_end')} f={(x) => String(x).replace(/ \(.*\)$/, '')} /> },
              { label: L('IPO date', 'Tanggal IPO'), value: <Val v={v('ipo_date')} f={(x) => dateShort(x)} /> },
            ]} />
        )
      })()}

      <DataCard q={own} title={t('ownership')} info="holders" h={220} ai="ownership_sentiment">
        {(d) => <Ownership d={d} rate={rate} />}
      </DataCard>

      <DataCard q={prof} title={t('similar')} info="peers">
        {(p) => {
          const peers = (p.peers?.value ?? []) as string[]
          return !peers.length ? <Empty icon="people">{L('No similar companies listed for this stock.', 'Tidak ada perusahaan sejenis untuk saham ini.')}</Empty> : (
            <>
              <div className="flex flex-wrap gap-2">
                {peers.map((x) => <button key={x} type="button" className={chip} onClick={() => { s.setTicker(x); scrollTo({ top: 0 }); document.querySelector('.phone-scroll')?.scrollTo({ top: 0 }) }}>{x}</button>)}
              </div>
              <p className="t-action text-dgrey mt-3 mb-0">{L('Tap one to open that stock.', 'Ketuk untuk membuka saham itu.')}</p>
            </>
          )
        }}
      </DataCard>

      <section>
        <h2 className="t-link text-navy m-0">{t('featured')}</h2>
        <div className="overflow-x-auto no-scrollbar mt-4 -mx-6">
          <div className="flex flex-col gap-4 px-6 w-max">
            {FEATURED.map((row, r) => (
              <div key={r} className="flex gap-2">{row.map((c) => <button key={c} type="button" className={chip} onClick={() => onToast(L('Prototype only', 'Hanya prototipe'))}>{c}</button>)}</div>
            ))}
          </div>
        </div>
      </section>
    </>
  )
}

const HOLDER_ID: Record<string, string> = { Insiders: 'Orang dalam', Institutions: 'Institusi', Other: 'Lainnya', Public: 'Publik', 'Public & other': 'Publik & lainnya' }

function Ownership({ d, rate }: { d: any; rate: number }) {
  const L = useL()
  const hb = d.holder_breakdown?.value as Record<string, number> | null
  const colors = [C.purple, C.blue, C.grey2]
  const pie = hb ? Object.entries(hb).map(([name, value]) => ({ name, value: Math.max(0, value) })) : []
  const inst = (d.top_institutions?.items ?? []).slice(0, 5)
  const monthly = (d.insider_monthly_net?.items ?? []).slice(-12).map((m: any) => ({ ...m, m: String(m.month).slice(2, 7), net: (m.net ?? 0) * rate }))
  const sh = d.short_interest?.value
  return (
    <>
      {hb ? (
        <div className="flex items-center gap-4">
          <div className="size-[120px] shrink-0">
            <PieChart width={120} height={120}>
              <Pie data={pie} dataKey="value" innerRadius={36} outerRadius={56} startAngle={90} endAngle={-270} stroke="none" isAnimationActive={false}>
                {pie.map((_, i) => <Cell key={i} fill={colors[i % 3]} />)}
              </Pie>
            </PieChart>
          </div>
          <div className="flex flex-col gap-2">
            {pie.map((x, i) => (
              <div key={x.name} className="flex items-center gap-2 t-label-m text-navy">
                <span className="size-2.5 rounded-sm" style={{ background: colors[i % 3] }} />{L(x.name, HOLDER_ID[x.name] ?? x.name)}<b className="ml-auto pl-2">{pct(x.value, 1)}</b>
              </div>
            ))}
          </div>
        </div>
      ) : <NA reason={d.holder_breakdown?.na_reason} />}

      <div className="t-label text-navy mt-5">{L('Top institutional holders', 'Pemegang institusi terbesar')}</div>
      {inst.length ? (
        <div className="flex flex-col gap-3 mt-2">
          {inst.map((h: any) => <Row key={h.holder} label={<span className="t-label-m">{h.holder}</span>} value={h['% of shares'] != null ? pct(h['% of shares'], 2) : '—'} />)}
        </div>
      ) : <div className="mt-1"><NA reason={d.top_institutions?.na_reason} /></div>}

      <div className="t-label text-navy mt-5">{L('Insider buying / selling per month', 'Pembelian / penjualan orang dalam per bulan')}</div>
      {monthly.length ? (
        <>
          <ChartBox h={150}>
            <BarChart data={monthly} margin={{ top: 8, right: 0, left: -4, bottom: 0 }}>
              <XAxis dataKey="m" tick={axisTick} axisLine={false} tickLine={false} interval="preserveStartEnd" />
              <YAxis tick={axisTick} axisLine={false} tickLine={false} width={48} tickFormatter={(v) => rpShort(v, 0).replace('Rp ', '')} />
              <ReferenceLine y={0} stroke={C.grey} />
              <TapTip fmt={(v) => rpShort(v, 1)} />
              <Bar isAnimationActive={false} dataKey="net" name={L('Net (bought − sold)', 'Bersih (beli − jual)')}>
                {monthly.map((m: any, i: number) => <Cell key={i} fill={m.net >= 0 ? C.green : C.red} />)}
              </Bar>
            </BarChart>
          </ChartBox>
          <Legend items={[[L('Net buying', 'Beli bersih'), C.green], [L('Net selling', 'Jual bersih'), C.red]]} />
        </>
      ) : <div className="mt-1 t-label-m text-dgrey">{d.insider_monthly_net?.na_reason && /licen|requires/i.test(d.insider_monthly_net.na_reason) ? <NA reason={d.insider_monthly_net.na_reason} /> : L('No insider trades in the last 12 months.', 'Tidak ada transaksi orang dalam dalam 12 bulan terakhir.')}</div>}

      <div className="t-label text-navy mt-5">{L('Short interest', 'Short interest')}</div>
      {sh ? (
        <div className="flex flex-col gap-3 mt-2">
          <Row label={L('Shares sold short', 'Saham yang di-short')} value={sh.pct_float != null ? L(`${pct(sh.pct_float, 1)} of float`, `${pct(sh.pct_float, 1)} dari float`) : '—'} />
          <Row label={L('Days to cover', 'Hari untuk menutup')} value={sh.days_to_cover != null ? num(sh.days_to_cover, 1) : '—'} />

        </div>
      ) : <div className="mt-1"><NA reason={d.short_interest?.na_reason} /></div>}
    </>
  )
}
