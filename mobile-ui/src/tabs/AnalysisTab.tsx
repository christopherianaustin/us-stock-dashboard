import { PolarAngleAxis, PolarGrid, PolarRadiusAxis, Radar, RadarChart } from 'recharts'
import { ep, useData, useSettings, type V } from '../lib/data'
import { byUnit, num, shortName } from '../lib/format'
import { glossary, useL, useT } from '../lib/i18n'
import * as P from '../lib/plain'
import { AnalystCard, ForecastCard } from '../components/Cards'
import { ChartBox, C } from '../components/charts'
import { Badge, DataCard, Empty, ErrorLine, Skeleton, ToneChip, useSheet } from '../components/ui'

type Pillar = { pillar: string; label: string; score: number | null; level: string | null; level_label: string; metrics_used: number; metrics_total: number; explanation: string }
const LEVEL_TONE: Record<string, P.Tone> = { strong: 'good', neutral: 'neutral', weak: 'watch' }

export function AnalysisTab({ rate, priceUsd }: { rate: number; priceUsd: number | null }) {
  const t = useT()
  const L = useL()
  const s = useSettings()
  const sum = useData<any>(ep.summary)
  const own = useData<any>(ep.ownership)
  const val = useData<any>(ep.valuation)
  const prof = useData<any>(ep.profile)

  return (
    <>
      {/* Stock analysis */}
      <DataCard q={sum} title={t('stock_analysis')} h={220} ai="summary"
        info={{ title: t('stock_analysis'), what: sum.data?.scorecard_note,
          how: (sum.data?.scorecard ?? []).map((p: Pillar) => `${p.label}: ${p.explanation}`).join('\n\n') }}>
        {(d) => d.scorecard?.length ? (
          <>
            <div className="flex flex-wrap gap-2">
              {d.scorecard.map((p: Pillar) => (
                <span key={p.pillar} className="inline-flex items-center gap-1.5 rounded-full border border-grey2 pl-3 pr-1 py-1">
                  <span className="t-label-m text-navy">{p.label}</span>
                  <ToneChip tone={p.level ? LEVEL_TONE[p.level] ?? 'na' : 'na'}>{p.level_label ?? 'N/A'}</ToneChip>
                </span>
              ))}
            </div>
            <List title={t('looks_good')} items={d.strengths.slice(0, 3)} good />
            <List title={t('to_watch')} items={d.risks.slice(0, 3)} />
            <p className="t-action text-dgrey mt-4 mb-0">{t('not_advice')}</p>
          </>
        ) : <Empty icon="doc">{L('The analysis needs financial statements, which are not available for this company.', 'Analisis ini butuh laporan keuangan, yang tidak tersedia untuk perusahaan ini.')}</Empty>}
      </DataCard>

      {/* Key stats: horizontal cards */}
      <section>
        <h2 className="t-link text-navy m-0">{t('key_stats')}</h2>
        {sum.loading || val.loading ? (
          <div className="flex gap-3 mt-3 overflow-hidden">{[0, 1, 2].map((i) => <Skeleton key={i} h={132} className="w-[148px] shrink-0" />)}</div>
        ) : sum.data ? (
          <KeyStats ks={sum.data.key_stats} peers={sum.data.peer_medians?.value} rate={rate}
            pePct={val.data?.history_stats?.pe?.value?.percentile ?? null} isFin={!!prof.data?.is_financial_company} />
        ) : <div className="mt-3 bg-white rounded-2xl shadow-card p-4"><ErrorLine onRetry={() => { sum.retry(); val.retry() }} detail={sum.error ?? val.error} kind={sum.errKind ?? val.errKind} /></div>}
      </section>

      {/* Wall Street analyst ratings (existing card) */}
      <DataCard q={own} title={t('analyst_ratings')} info="analyst_ratings" h={260}>
        {(d) => {
          const c = d.analyst_consensus?.value?.counts
          if (!c) return <Empty icon="people">{d.analyst_consensus?.na_reason && !/^N\/A/.test(d.analyst_consensus.na_reason) ? d.analyst_consensus.na_reason : L('No Wall Street analysts cover this stock right now.', 'Belum ada analis Wall Street yang meliput saham ini.')}</Empty>
          return <AnalystCard ticker={s.ticker} tag={d.analyst_consensus.license_tag}
            counts={[c.strongBuy, c.buy, c.hold, c.sell, c.strongSell].map((x: number) => x ?? 0)} />
        }}
      </DataCard>

      {/* Price target forecast (existing card) */}
      <DataCard q={val} title={t('price_target')} info="target_upside" flush h={300}>
        {(d) => {
          const tg = d.analyst_targets?.value
          if (!tg || priceUsd == null) return <div className="px-4 pb-4"><Empty icon="chart">{L('No analyst price targets for this stock.', 'Tidak ada target harga analis untuk saham ini.')}{d.analyst_targets?.na_reason ? ` (${d.analyst_targets.na_reason.replace(/^N\/A\s*\(?|\)$/g, '')})` : ''}</Empty></div>
          return <ForecastCard name={shortName(sum.data?.header?.name?.value ?? s.ticker)} cur={priceUsd}
            lowUsd={tg.low} meanUsd={tg.mean} highUsd={tg.high} updated={val.env!.generated_at} rate={rate} tag={d.analyst_targets.license_tag} />
        }}
      </DataCard>

      {/* How we scored this */}
      <DataCard q={sum} title={t('how_scored')} defaultOpen={false}>
        {(d) => !d.scorecard?.length ? <Empty>{L('Not available.', 'Tidak tersedia.')}</Empty> : (
          <>
            <ChartBox h={240}>
              <RadarChart data={d.scorecard.map((p: Pillar) => ({ k: p.label, v: p.score ?? 0 }))} outerRadius="70%">
                <PolarGrid stroke={C.grey2} />
                <PolarAngleAxis dataKey="k" tick={{ fill: C.navy, fontSize: 10, fontWeight: 700 }} />
                <PolarRadiusAxis domain={[0, 100]} tick={false} axisLine={false} />
                <Radar isAnimationActive={false} dataKey="v" stroke={C.purple} fill={C.purple} fillOpacity={0.25} />
              </RadarChart>
            </ChartBox>
            <div className="flex flex-col gap-3 mt-2">
              {d.scorecard.map((p: Pillar) => (
                <div key={p.pillar} className="flex items-center justify-between gap-2">
                  <div>
                    <div className="t-label text-navy">{p.label}</div>
                    <div className="t-action text-dgrey">{L(`based on ${p.metrics_used} of ${p.metrics_total} metrics`, `berdasarkan ${p.metrics_used} dari ${p.metrics_total} metrik`)}</div>
                  </div>
                  <span className="t-link text-navy">{p.score == null ? 'N/A' : `${num(p.score)}/100`}</span>
                </div>
              ))}
            </div>
            <p className="t-action text-dgrey mt-4 mb-0">{L('Strong = 70+, Neutral = 40-69, Weak = under 40.', 'Kuat = 70+, Netral = 40-69, Lemah = di bawah 40.')} {t('not_advice')}</p>
          </>
        )}
      </DataCard>
    </>
  )
}

function List({ title, items, good = false }: { title: string; items: string[]; good?: boolean }) {
  if (!items.length) return null
  return (
    <div className="mt-4">
      <div className="t-label text-navy">{title}</div>
      <ul className="list-none p-0 m-0 mt-2 flex flex-col gap-2">
        {items.map((x) => (
          <li key={x} className="flex gap-2 t-label-m text-navy">
            <span className={`size-5 rounded-full grid place-items-center shrink-0 mt-px text-[11px] font-bold ${good ? 'bg-up-bg text-up' : 'bg-[#FFF4E0] text-amber-600'}`}>{good ? '✓' : '!'}</span>
            <span>{x}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

/* ---------- Key stats as sideways cards; tap one for the explanation ---------- */
const STATS: { k: string; g: string; label: string; id: string }[] = [
  { k: 'pe', g: 'pe', label: 'P/E', id: 'P/E' }, { k: 'ps', g: 'ps', label: 'P/S', id: 'P/S' }, { k: 'ev_ebitda', g: 'ev_ebitda', label: 'EV/EBITDA', id: 'EV/EBITDA' },
  { k: 'revenue_yoy', g: 'growth', label: 'Revenue growth', id: 'Pertumbuhan pendapatan' }, { k: 'net_margin', g: 'margins', label: 'Net margin', id: 'Margin bersih' },
  { k: 'roe', g: 'roe', label: 'ROE', id: 'ROE' }, { k: 'debt_to_equity', g: 'debt_to_equity', label: 'Debt to equity', id: 'Utang terhadap ekuitas' },
  { k: 'dividend_yield', g: 'dividend_yield', label: 'Dividend yield', id: 'Imbal hasil dividen' }, { k: 'beta', g: 'beta', label: 'Beta', id: 'Beta' },
]

function KeyStats({ ks, peers, pePct, rate, isFin }: { ks: Record<string, V>; peers: any; pePct: number | null; rate: number; isFin: boolean }) {
  const { lang } = useSettings()
  const open = useSheet()
  const explain = (k: string, v: number | null): P.Explained => {
    switch (k) {
      case 'pe': return P.peRatio(v, pePct, lang)
      case 'ps': return P.multiple(v, peers?.ps ?? null, lang, lang === 'id' ? 'penjualan' : 'sales')
      case 'ev_ebitda': return P.multiple(v, peers?.ev_ebitda ?? null, lang, lang === 'id' ? 'laba operasi (EBITDA)' : 'operating earnings (EBITDA)')
      case 'revenue_yoy': return P.revenueGrowth(v, lang)
      case 'net_margin': return P.netMargin(v, lang)
      case 'roe': return P.roe(v, lang)
      case 'debt_to_equity': return P.debtToEquity(v, lang, isFin && v == null)
      case 'dividend_yield': return P.dividendYield(v, !!ks.dividend_yield, lang)
      default: return P.beta(v, lang)
    }
  }
  return (
    <div className="flex gap-3 overflow-x-auto no-scrollbar -mx-6 px-6 pt-3 pb-6 snap-x snap-mandatory scroll-px-6">
      {STATS.map(({ k, g, label: en, id }) => {
        const label = lang === 'id' ? id : en
        const v = ks[k] as V | undefined
        const x = v?.value ?? null
        const e = explain(k, x)
        const shown = x == null ? null : byUnit(x, v?.unit ?? (k === 'beta' ? 'x' : 'ratio'), rate)
        const gl = glossary(lang, g)
        return (
          <button key={k} type="button" onClick={() => open({ title: gl?.label ?? label, what: gl?.what, how: gl?.how, good_bad: gl?.good_bad,
            extra: e.sentence ? <p className="t-body text-navy m-0 bg-lavender rounded-xl p-3">{e.sentence}</p> : undefined })}
            aria-label={`${label}: ${shown ?? 'N/A'}. ${e.label}`}
            className="snap-start shrink-0 w-[148px] min-h-[132px] bg-white rounded-2xl shadow-card p-3 text-left border-0 cursor-pointer flex flex-col">

            <span className="t-label-m text-dgrey">{label}</span>
            <span className="t-subtitle text-navy mt-1">{shown ?? (k === 'dividend_yield' && !ks.dividend_yield ? '—' : 'N/A')}</span>
            {x == null && v?.na_reason && <span className="t-action text-grey">{v.na_reason}</span>}
            <span className="mt-auto pt-2"><ToneChip tone={e.tone}>{e.label}</ToneChip></span>
            <Badge tag={v?.license_tag} />
          </button>
        )
      })}
    </div>
  )
}
