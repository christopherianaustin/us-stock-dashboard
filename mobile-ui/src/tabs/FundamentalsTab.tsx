import { Bar, BarChart, Line, LineChart, ReferenceArea, ReferenceLine, XAxis, YAxis } from 'recharts'
import { ep, useData, useSettings, type V } from '../lib/data'
import { dateShort, num, pct, pctSigned, rp, rpS } from '../lib/format'
import { useL, useT } from '../lib/i18n'
import * as P from '../lib/plain'
import { C, ChartBox, TapTip, axisTick } from '../components/charts'
import { DataCard, Empty, NA, Row, ToneChip, Val } from '../components/ui'

const x2 = (v: number) => `${num(v, 2)}x`

export function FundamentalsTab({ rate, priceUsd }: { rate: number; priceUsd: number | null }) {
  const t = useT()
  const L = useL()
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
      <DataCard q={rat} title={t('valuation')} info="valuation_history" h={260} ai="valuation">
        {(r) => {
          const hs = val.data?.history_stats ?? {}
          const pm = val.data?.peer_medians?.value ?? {}
          const cmp = (k: string) => {
            const med = hs[k]?.value?.median, peer = pm[k]
            const parts = [med != null && `${L('5-yr median', 'median 5 thn')} ${x2(med)}`, peer != null && `${L('peers', 'sejenis')} ${x2(peer)}`].filter(Boolean)
            return parts.length ? parts.join(' · ') : undefined
          }
          const pe = hs.pe?.value
          const hist = (val.data?.history_weekly?.items ?? []).filter((h: any) => h.pe != null)
          return (
            <>
              <div className="flex flex-col gap-4">
                <Row label={L('Share price', 'Harga saham')} value={<Val v={sum.data?.header?.price} f={(x) => rp(x, rate)} />} />
                <Row label={L('Market cap', 'Kapitalisasi pasar')} value={<Val v={sum.data?.header?.market_cap} f={(x) => rpS(x, rate)} />} />
                <Row label="P/E" value={<Val v={r.pe} f={x2} />} sub={cmp('pe')} />
                <Row label="P/S" value={<Val v={r.ps} f={x2} />} sub={cmp('ps')} />
                <Row label="P/B" value={<Val v={r.pb} f={x2} />} />
                <Row label="EV/EBITDA" value={<Val v={r.ev_ebitda} f={x2} />} sub={cmp('ev_ebitda')} />
                <Row label={L('FCF yield', 'Imbal hasil FCF')} value={<Val v={r.fcf_yield} f={(x) => pct(x)} />} />
              </div>
              {hist.length > 10 && pe && (
                <div className="mt-5">
                  <div className="t-label text-navy">{L('P/E over 5 years', 'P/E selama 5 tahun')}</div>
                  <ChartBox h={160}>
                    <LineChart data={hist} margin={{ top: 8, right: 4, left: -18, bottom: 0 }}>
                      <ReferenceArea y1={Math.max(pe.low, pe.median - pe.std)} y2={Math.min(pe.high, pe.median + pe.std)} fill={C.purple} fillOpacity={0.07} />
                      <ReferenceLine y={pe.median} stroke={C.purple} strokeDasharray="4 3" label={{ value: L('median', 'median'), fill: C.purple, fontSize: 10, position: 'insideTopLeft' }} />
                      <XAxis dataKey="date" tick={axisTick} tickFormatter={(d) => String(d).slice(0, 4)} interval="preserveStartEnd" minTickGap={40} axisLine={false} tickLine={false} />
                      <YAxis tick={axisTick} axisLine={false} tickLine={false} width={44} />
                      <TapTip fmt={(v) => x2(v)} />
                      <Line isAnimationActive={false} dataKey="pe" name="P/E" stroke={C.navy} strokeWidth={2} dot={false} />
                    </LineChart>
                  </ChartBox>
                  <p className="t-label-m text-navy mt-2 mb-0">
                    {L(`P/E is higher than ${num(pe.percentile * 100)}% of the last 5 years.`, `P/E lebih tinggi dari ${num(pe.percentile * 100)}% waktu dalam 5 tahun terakhir.`)}
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
      <DataCard q={rat} title={t('profitability')} info="roe" defaultOpen={false} ai="profitability_health">
        {(r) => (
          <>
            <div className="flex flex-col gap-4">
              {([['ROE', 'roe', 0.15, 0.08], ['ROA', 'roa', 0.08, 0.03], ['ROIC', 'roic', 0.12, 0.06],
                [L('Gross margin (TTM)', 'Margin kotor (TTM)'), 'gross_margin', 0.4, 0.2], [L('Operating margin (TTM)', 'Margin operasi (TTM)'), 'operating_margin', 0.15, 0.05],
                [L('Net margin (TTM)', 'Margin bersih (TTM)'), 'net_margin', 0.15, 0.05]] as const).map(([l, k, g, o]) => (
                <Row key={k} label={l} value={<span className="inline-flex items-center gap-2">
                  {r[k]?.value != null && <ToneChip tone={P.simpleLevel(r[k].value, g, o, lang).tone}>{P.simpleLevel(r[k].value, g, o, lang).label}</ToneChip>}
                  <Val v={r[k]} f={(x) => pct(x)} /></span>} />
              ))}
            </div>
            <div className="mt-5 rounded-xl bg-lgrey p-3">
              <div className="t-label text-navy">{L('Where ROE comes from', 'Dari mana ROE berasal')}</div>
              <div className="flex flex-col gap-2 mt-2">
                <Row label={L('Net margin', 'Margin bersih')} value={<Val v={r.net_margin} f={(x) => pct(x)} />} />
                <Row label={L('× Asset turnover', '× Perputaran aset')} value={<Val v={r.asset_turnover} f={x2} />} />
                <Row label={L('× Leverage', '× Leverage')} value={<Val v={r.equity_multiplier} f={x2} />} />
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
            {([[L('Revenue vs last year', 'Pendapatan vs tahun lalu'), 'revenue_yoy'], [L('EPS vs last year', 'EPS vs tahun lalu'), 'eps_yoy'],
              [L('Revenue, 3 yrs (per year)', 'Pendapatan, 3 thn (per tahun)'), 'revenue_cagr_3y'], [L('Revenue, 5 yrs (per year)', 'Pendapatan, 5 thn (per tahun)'), 'revenue_cagr_5y'],
              [L('EPS, 3 yrs (per year)', 'EPS, 3 thn (per tahun)'), 'eps_cagr_3y'], [L('EPS, 5 yrs (per year)', 'EPS, 5 thn (per tahun)'), 'eps_cagr_5y']] as const).map(([l, k]) => (
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
      <DataCard q={div} title={t('dividends')} info="dividend_yield" defaultOpen={false} ai="dividends">
        {(d) => !d.pays_dividend ? <Empty icon="coin">{L('This company does not pay a dividend. Profits are kept in the business or used to buy back shares.', 'Perusahaan ini tidak membagikan dividen. Laba disimpan di bisnis atau dipakai untuk membeli kembali saham.')}</Empty> : <Dividends d={d} rate={rate} />}
      </DataCard>
    </>
  )
}

/* ---------- Fair value: today's price vs Graham number, DCF scenarios and analysts' mean target ---------- */
function FairValue({ d, rate, priceUsd }: { d: any; rate: number; priceUsd: number | null }) {
  const t = useT()
  const L = useL()
  const sc = d.dcf?.scenarios ?? {}
  const items: { label: string; v: V | undefined; color: string }[] = [
    { label: L('Graham number', 'Angka Graham'), v: d.graham_number, color: C.blue },
    { label: L('DCF · bear case', 'DCF · skenario buruk'), v: sc.Bear, color: C.red },
    { label: L('DCF · base case', 'DCF · skenario dasar'), v: sc.Base, color: C.purple },
    { label: L('DCF · bull case', 'DCF · skenario baik'), v: sc.Bull, color: C.green },
    { label: L("Analysts' mean target", 'Target rata-rata analis'), v: d.analyst_targets ? { ...d.analyst_targets, value: d.analyst_targets.value?.mean ?? null } : undefined, color: C.amber },
  ]
  if (priceUsd == null) return <NA reason={L('Price not available', 'Harga tidak tersedia')} />
  const vals = items.map((i) => (i.v?.value as number | null) ?? null).filter((x): x is number => x != null && x > 0)
  const max = Math.max(priceUsd, ...vals) * 1.08
  const pos = (x: number) => `${Math.min(100, (x / max) * 100)}%`
  return (
    <>
      <div className="rounded-xl bg-down-bg/60 px-3 py-2 t-label text-navy text-center">{t('estimate')}</div>
      <div className="flex flex-col gap-4 mt-4">
        <FvRow label={L("Today's price", 'Harga hari ini')} value={rp(priceUsd, rate)} pos={pos(priceUsd)} color={C.ink} bold />
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
          {L(`DCF assumptions: cash flow grows ${pct(d.dcf.assumptions.growth, 1)} a year (${d.dcf.assumptions.growth_source}), discount rate ${pct(d.dcf.assumptions.discount_rate, 0)}, long-term growth ${pct(d.dcf.assumptions.terminal_growth, 1)}. Bear / bull change growth down / up.`,
            `Asumsi DCF: arus kas tumbuh ${pct(d.dcf.assumptions.growth, 1)} per tahun (${d.dcf.assumptions.growth_source}), tingkat diskonto ${pct(d.dcf.assumptions.discount_rate, 0)}, pertumbuhan jangka panjang ${pct(d.dcf.assumptions.terminal_growth, 1)}. Skenario buruk / baik menurunkan / menaikkan pertumbuhan.`)}
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
  const L = useL()
  const pio = r.piotroski
  const alt = r.altman_z
  const z = alt?.value as number | null
  return (
    <>
      <div className="flex items-center justify-between">
        <span className="t-label text-navy">{L('Piotroski score', 'Skor Piotroski')}</span>
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
          <div className="flex justify-between t-action text-dgrey"><span>{L('Distress', 'Bahaya')}</span><span>{L('Grey', 'Abu-abu')}</span><span>{L('Safe', 'Aman')}</span></div>
          <p className="t-action text-dgrey mt-1 mb-0">{L('Scale capped at 6.', 'Skala dibatasi sampai 6.')}</p>
        </div>
      ) : <div className="mt-1"><NA reason={alt?.na_reason ?? (isFin ? L('Not meaningful for banks', 'Tidak bermakna untuk bank') : undefined)} /></div>}

      <div className="mt-5 t-label text-navy">{L('Debt & cash', 'Utang & kas')}</div>
      <div className="flex flex-col gap-3 mt-2">
        <Row label={L('Net debt', 'Utang bersih')} value={<Val v={r.net_debt} f={(x) => rpS(x, rate)} />} />
        <Row label={L('Debt to equity', 'Utang terhadap ekuitas')} value={<Val v={r.debt_to_equity} f={x2} />} />
        <Row label={L('Current ratio', 'Rasio lancar')} value={<Val v={r.current_ratio} f={x2} />} />
        <Row label={L('Interest coverage', 'Cakupan bunga')} value={<Val v={r.interest_coverage} f={x2} />} />
      </div>
    </>
  )
}

/* ---------- Dividends ---------- */
function Dividends({ d, rate }: { d: any; rate: number }) {
  const L = useL()
  const thisYear = new Date().getFullYear()
  const bars = Object.entries((d.annual_dps?.value ?? {}) as Record<string, number>)
    .filter(([y]) => Number(y) < thisYear).slice(-8).map(([y, v]) => ({ y, v: v * rate }))
  return (
    <>
      <div className="flex flex-col gap-4">
        <Row label={L('Dividend yield', 'Imbal hasil dividen')} value={<Val v={d.yield_ttm} f={(x) => pct(x)} />} />
        <Row label={L('Payout ratio', 'Rasio pembayaran')} value={<Val v={d.payout_ratio} f={(x) => pct(x, 0)} />} />
        <Row label={L('Years of raises', 'Tahun kenaikan beruntun')} value={<Val v={d.growth_streak_years} f={(x) => L(`${x} years`, `${x} tahun`)} />} />
        <Row label={L('Next ex-dividend date', 'Tanggal ex-dividen berikutnya')} value={<Val v={d.next_ex_dividend_date} f={(x) => dateShort(x)} />} />
      </div>
      {bars.length > 1 && (
        <div className="mt-5">
          <div className="t-label text-navy">{L('Dividend per share by year', 'Dividen per saham per tahun')}</div>
          <ChartBox h={160}>
            <BarChart data={bars} margin={{ top: 8, right: 0, left: -6, bottom: 0 }}>
              <XAxis dataKey="y" tick={axisTick} axisLine={false} tickLine={false} />
              <YAxis tick={axisTick} axisLine={false} tickLine={false} width={50} tickFormatter={(v) => `${num(v / 1000)}K`} />
              <TapTip fmt={(v) => `Rp ${num(v)}`} />
              <Bar isAnimationActive={false} dataKey="v" name={L('Dividend', 'Dividen')} fill={C.purple} radius={[4, 4, 0, 0]} />

            </BarChart>
          </ChartBox>
        </div>
      )}
    </>
  )
}

