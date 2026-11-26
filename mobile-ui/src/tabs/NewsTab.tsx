import { useState } from 'react'
import { ep, useData } from '../lib/data'
import { ago, dateShort } from '../lib/format'
import { useL, useT } from '../lib/i18n'
import bloomberg from '../assets/figma/news-bloomberg.svg'
import cnn from '../assets/figma/news-cnn.svg'
import { Badge, DataCard, Empty, Pills } from '../components/ui'

type News = { datetime: string; headline: string; source: string; url: string; summary?: string }
type Filing = { form: string; filing_date: string; description?: string; items?: string | null; url: string }

const LOGOS: Record<string, { logo: string; bg: string }> = {
  bloomberg: { logo: bloomberg, bg: 'linear-gradient(151.9deg,#2800D7 31.9%,#D10087 90.2%)' },
  cnn: { logo: cnn, bg: '#CB2026' },
}
const PALETTE = ['#561FA3', '#082F57', '#06CB90', '#E11C23', '#52B1FE', '#F5A524', '#7C8D9D']

/** Source logo: the Figma Bloomberg / CNN marks, otherwise the source's initials in a coloured circle. */
function SourceAvatar({ name }: { name: string }) {
  const k = name.toLowerCase()
  const known = LOGOS[k]
  if (known) return (
    <span className="relative size-6 rounded-full shrink-0" style={{ background: known.bg }}>
      <img src={known.logo} alt="" className="absolute inset-[20%] size-[60%]" />
    </span>
  )
  const color = PALETTE[[...k].reduce((a, c) => a + c.charCodeAt(0), 0) % PALETTE.length]
  return <span className="size-6 rounded-full shrink-0 grid place-items-center text-white text-[10px] font-bold" style={{ background: color }}>{name.slice(0, 1).toUpperCase()}</span>
}

/** Plain description of an SEC form. 8-K item 2.02 = results of operations (earnings). */
function formText(f: Filing, L: (en: string, id: string) => string) {
  const items = f.items ?? ''
  switch (f.form) {
    case '10-K': return L('Annual report', 'Laporan tahunan')
    case '10-Q': return L('Quarterly report', 'Laporan kuartalan')
    case '8-K': return items.includes('2.02') ? L('Earnings results', 'Hasil laba') : L('Company news (current report)', 'Berita perusahaan (laporan terkini)')
    case '4': return L('Insider trade', 'Transaksi orang dalam')
    case '3': return L('New insider', 'Orang dalam baru')
    case 'DEF 14A': return L('Shareholder meeting', 'Rapat pemegang saham')
    case 'SC 13G': case 'SC 13G/A': case 'SCHEDULE 13G': case 'SCHEDULE 13G/A': return L('Large shareholder', 'Pemegang saham besar')
    case '144': return L('Planned insider sale', 'Rencana penjualan orang dalam')
    case 'S-8': return L('Employee share plan', 'Program saham karyawan')
    default: return f.description && f.description !== f.form ? f.description : L('Filing', 'Laporan')
  }
}

export function NewsTab() {
  const t = useT()
  const L = useL()
  const q = useData<any>(ep.news)
  const [days, setDays] = useState<'7' | '30'>('7')
  const [shown, setShown] = useState(10)

  return (
    <>
      <DataCard q={q} title={t('latest_news')} info="news" h={300} ai="news_filings">
        {(d) => {
          if (!d.news?.available) return <Empty icon="news">{L('News is not available right now.', 'Berita sedang tidak tersedia.')}{d.news?.na_reason ? ` (${d.news.na_reason.replace(/^N\/A\s*\(?|\)$/g, '')})` : ''}</Empty>
          // count back from when the data was fetched (saved data may be a few days old)
          const cutoff = new Date(q.env?.generated_at ?? Date.now()).getTime() - Number(days) * 864e5
          const items: News[] = d.news.items.filter((n: News) => new Date(n.datetime).getTime() >= cutoff)
          return (
            <>
              <div className="flex items-center justify-between">
                <Pills small label={L('Period', 'Periode')} value={days} onChange={(k) => { setDays(k); setShown(10) }}
                  options={[{ key: '7', label: L('7 days', '7 hari') }, { key: '30', label: L('30 days', '30 hari') }]} />
                <Badge tag={d.news.license_tag} />
              </div>
              {!items.length ? <div className="mt-4"><Empty icon="news">{L(`No news about this stock in the last ${days} days.`, `Tidak ada berita tentang saham ini dalam ${days} hari terakhir.`)}</Empty></div> : (
                <ul className="list-none m-0 p-0 mt-4 flex flex-col gap-3">
                  {items.slice(0, shown).map((n, i) => (
                    <li key={i}>
                      <a href={n.url} target="_blank" rel="noreferrer noopener"
                        className="block rounded-2xl border border-grey2 p-3 no-underline active:bg-lgrey">
                        <div className="flex items-center gap-2">
                          <SourceAvatar name={n.source} />
                          <span className="t-label text-navy">{n.source}</span>
                          <span className="t-action text-dgrey ml-auto">{ago(n.datetime)}</span>
                        </div>
                        <p className="t-label-m text-navy mt-2 mb-0 line-clamp-3">{n.headline}</p>
                      </a>
                    </li>
                  ))}
                </ul>
              )}
              {items.length > shown && (
                <button type="button" onClick={() => setShown(shown + 10)} className="mt-3 t-link text-purple bg-transparent border-0 p-0 cursor-pointer">{L(`Show more (${items.length - shown})`, `Tampilkan lagi (${items.length - shown})`)}</button>
              )}
            </>
          )
        }}
      </DataCard>

      <DataCard q={q} title={t('sec_filings')} info="sec_filings" defaultOpen h={200}>
        {(d) => !d.sec_filings?.items?.length ? <Empty icon="doc">{L('No SEC filings found for this company.', 'Tidak ada laporan SEC untuk perusahaan ini.')}</Empty> : (
          <ul className="list-none m-0 p-0 flex flex-col">
            {d.sec_filings.items.slice(0, 12).map((f: Filing, i: number) => (
              <li key={i} className="border-b border-grey2 last:border-0">
                <a href={f.url} target="_blank" rel="noreferrer noopener" className="flex items-center gap-3 py-2.5 no-underline">
                  <span className="t-action-b text-purple bg-lavender rounded-md px-1.5 py-0.5 min-w-[44px] text-center">{f.form}</span>
                  <span className="flex-1 t-label-m text-navy">{formText(f, L)}</span>

                  <span className="t-action text-dgrey whitespace-nowrap">{dateShort(f.filing_date)}</span>
                </a>
              </li>
            ))}
          </ul>
        )}
      </DataCard>
    </>
  )
}
