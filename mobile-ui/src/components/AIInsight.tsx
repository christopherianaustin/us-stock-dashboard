// AI Insight block (SPEC 15.7, step 10c): shown at the top of a section, generated only when it scrolls into view.
// Fails quietly: if the API is off, AI is switched off, or the request fails, the block simply isn't there.
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { API } from '../config'
import { ep, useData, useSettings, type AiTab } from '../lib/data'
import { dateShort } from '../lib/format'
import { useL } from '../lib/i18n'
import type { Tone } from '../lib/plain'
import { ToneChip } from './ui'

type Point = { text: string; metric_keys: string[] }
type Summary = {
  signal: string; headline?: string; takeaway?: string; label?: string
  positives: (Point | string)[]; watch_outs: (Point | string)[]
  what_to_watch_next?: string[]; ask_yourself?: string; data_gaps?: string[]
}
type AiRes = {
  enabled: boolean; source?: 'ai' | 'fallback'; ticker?: string; tab?: AiTab; lang?: string
  prompt_version?: string; as_of?: string | null; summary?: Summary
}

const TONE: Record<string, Tone> = { Strong: 'good', Neutral: 'neutral', Weak: 'watch' }
const SIGNAL_ID: Record<string, string> = {
  Strong: 'Kuat', Neutral: 'Netral', Weak: 'Lemah', 'Not enough data': 'Data belum cukup', 'Not applicable': 'Tidak berlaku',
}

const Sparkle = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" aria-hidden className="shrink-0">
    <path fill="#561FA3" d="M12 2l1.9 5.6L19.5 9.5l-5.6 1.9L12 17l-1.9-5.6L4.5 9.5l5.6-1.9zM19 14l.9 2.6 2.6.9-2.6.9L19 21l-.9-2.6-2.6-.9 2.6-.9z" />
  </svg>
)
const Thumb = ({ down = false, on }: { down?: boolean; on: boolean }) => (
  <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden style={{ transform: down ? 'rotate(180deg)' : undefined }}>
    <path d="M7 10v11H3V10zM7 10l4-8c1.7 0 3 1.3 3 3v4h5.5c1.4 0 2.4 1.3 2 2.6l-2.3 7.6c-.3.8-1 1.4-1.9 1.4H7"
      fill={on ? '#561FA3' : 'none'} stroke={on ? '#561FA3' : '#7C8D9D'} strokeWidth="1.8" strokeLinejoin="round" />
  </svg>
)

/** Waits until the block is near the screen, so sections the user never scrolls to cost nothing. */
export function AIInsight({ tab, standalone = false }: { tab: AiTab; standalone?: boolean }) {
  const ref = useRef<HTMLDivElement>(null)
  const [seen, setSeen] = useState(false)
  useEffect(() => {
    const el = ref.current
    if (!el || seen) return
    if (!('IntersectionObserver' in window)) { setSeen(true); return }
    const io = new IntersectionObserver((es) => es.some((e) => e.isIntersecting) && setSeen(true), { rootMargin: '200px' })
    io.observe(el)
    return () => io.disconnect()
  }, [seen])
  if (!seen) return <div ref={ref}><Loading standalone={standalone} /></div>
  return <Loaded tab={tab} standalone={standalone} />
}

function Shell({ standalone, children }: { standalone: boolean; children: ReactNode }) {
  return standalone
    ? <section className="bg-white rounded-2xl shadow-card p-4" data-ai-insight><div className="bg-lavender rounded-xl p-3">{children}</div></section>
    : <div className="bg-lavender rounded-xl p-3 mb-4" data-ai-insight>{children}</div>
}

function Loading({ standalone }: { standalone: boolean }) {
  const L = useL()
  const [slow, setSlow] = useState(false)
  useEffect(() => { const id = setTimeout(() => setSlow(true), 4000); return () => clearTimeout(id) }, [])
  return (
    <Shell standalone={standalone}>
      <div className="flex items-center gap-1.5" role="status" aria-label={L('Writing the AI Insight', 'Sedang menulis Insight AI')}>
        <Sparkle /><span className="t-action-b text-purple">{L('AI Insight', 'Insight AI')}</span>
      </div>
      <div className="skeleton h-3 rounded-full mt-3 w-3/5" data-skeleton />
      <div className="skeleton h-3 rounded-full mt-2 w-full" />
      <div className="skeleton h-3 rounded-full mt-2 w-4/5" />
      {slow && <p className="t-action text-dgrey mt-2 mb-0">{L('Writing a summary of this data. The first time can take up to a minute.', 'Sedang merangkum data ini. Pertama kali bisa sampai satu menit.')}</p>}
    </Shell>
  )
}

function Loaded({ tab, standalone }: { tab: AiTab; standalone: boolean }) {
  const s = useSettings()
  const L = useL()
  const q = useData<AiRes>((t, lang) => ep.ai(t, lang, tab))
  const [more, setMore] = useState(false)
  const [vote, setVote] = useState<'up' | 'down' | null>(null)
  useEffect(() => { setVote(null); setMore(false) }, [s.ticker, s.lang])

  if (q.loading) return <Loading standalone={standalone} />
  const d = q.data
  // No card when: the request failed, AI is switched off, or saved (demo) samples would be shown in safe mode.
  if (q.error || !d?.enabled || !d.summary || (q.src === 'mock' && s.safe)) return null
  const sm = d.summary
  const ai = d.source === 'ai'
  if (!ai && !sm.positives.length && !sm.watch_outs.length) return null

  const chip = <ToneChip tone={TONE[sm.signal] ?? 'na'}>{s.lang === 'id' ? SIGNAL_ID[sm.signal] ?? sm.signal : sm.signal}</ToneChip>
  const text = (p: Point | string) => (typeof p === 'string' ? p : p.text)
  const asOf = dateShort(d.as_of ?? q.env?.generated_at)
  const send = (v: 'up' | 'down') => {
    setVote(v)
    fetch(API.aiFeedback(), {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ticker: d.ticker ?? s.ticker, tab, lang: s.lang, prompt_version: d.prompt_version ?? '', vote: v, source: d.source, surface: 'mobile' }),
    }).catch(() => { /* saved-data mode / API down: the thanks message still shows */ })
  }

  return (
    <Shell standalone={standalone}>
      <div className="flex items-center gap-1.5 flex-wrap">
        {ai && <Sparkle />}
        <span className="t-action-b text-purple">{ai ? L('AI Insight', 'Insight AI') : sm.label ?? L('Automatic summary', 'Ringkasan otomatis')}</span>
        <span className="ml-auto">{chip}</span>
      </div>
      {ai && <p className="t-label text-navy mt-2 mb-0">{sm.headline}</p>}
      {ai && <p className="t-label-m text-navy mt-1 mb-0">{sm.takeaway}</p>}
      {(sm.positives.length > 0 || sm.watch_outs.length > 0) && (
        <ul className="list-none p-0 m-0 mt-3 flex flex-col gap-2">
          {sm.positives.map((p, i) => <Item key={`p${i}`} good text={text(p)} />)}
          {sm.watch_outs.map((p, i) => <Item key={`w${i}`} text={text(p)} />)}
        </ul>
      )}
      {ai && (
        <>
          <button type="button" onClick={() => setMore(!more)} aria-expanded={more}
            className="mt-3 p-0 bg-transparent border-0 t-action-b text-purple cursor-pointer">
            {more ? L('Less', 'Lebih sedikit') : L('More', 'Selengkapnya')}
          </button>
          {more && (
            <div className="mt-2 flex flex-col gap-2">
              {!!sm.what_to_watch_next?.length && (
                <div>
                  <div className="t-action-b text-dgrey">{L('What to watch next', 'Yang perlu dipantau')}</div>
                  {sm.what_to_watch_next.map((w, i) => <p key={i} className="t-label-m text-navy mt-1 mb-0">{w}</p>)}
                </div>
              )}
              {sm.ask_yourself && (
                <div>
                  <div className="t-action-b text-dgrey">{L('Ask yourself', 'Tanyakan pada diri sendiri')}</div>
                  <p className="t-label-m text-navy mt-1 mb-0">{sm.ask_yourself}</p>
                </div>
              )}
            </div>
          )}
        </>
      )}
      <p className="t-action text-dgrey mt-3 mb-0">
        {ai
          ? L(`AI-generated from the data on this page (as of ${asOf}). It can make mistakes and is not investment advice.`,
            `Dibuat oleh AI dari data di halaman ini (per ${asOf}). Bisa keliru dan bukan saran investasi.`)
          : L(`Automatic summary from our rule-based checks (as of ${asOf}). Not investment advice.`,
            `Ringkasan otomatis dari pemeriksaan berbasis aturan kami (per ${asOf}). Bukan saran investasi.`)}
      </p>
      <div className="flex items-center gap-1 mt-2">
        <span className="t-action text-dgrey mr-1">{vote ? L('Thanks for the feedback.', 'Terima kasih atas masukannya.') : L('Was this helpful?', 'Apakah ini membantu?')}</span>
        {(['up', 'down'] as const).map((v) => (
          <button key={v} type="button" onClick={() => send(v)} aria-pressed={vote === v} disabled={!!vote}
            aria-label={v === 'up' ? L('Helpful', 'Membantu') : L('Not helpful', 'Tidak membantu')}
            className="size-8 grid place-items-center rounded-full bg-white border-0 cursor-pointer disabled:cursor-default active:scale-95 transition-transform">
            <Thumb down={v === 'down'} on={vote === v} />
          </button>
        ))}
      </div>
    </Shell>
  )
}

function Item({ text, good = false }: { text: string; good?: boolean }) {
  return (
    <li className="flex gap-2 t-label-m text-navy">
      <span className={`size-2 rounded-full shrink-0 mt-1.5 ${good ? 'bg-up' : 'bg-amber-500'}`} aria-hidden />
      <span><span className="sr-only">{good ? 'Positive: ' : 'Watch-out: '}</span>{text}</span>
    </li>
  )
}
