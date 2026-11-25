import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import chevronUp from '../assets/figma/chevron-up.svg'
import infoIcon from '../assets/figma/info.svg'
import { useSettings, type Q, type V } from '../lib/data'
import { glossary, glossaryUi, useT } from '../lib/i18n'
import type { Tone } from '../lib/plain'

/* ---------- Icons (nav icons are drawn to match the Figma style: solid navy, 24 px) ---------- */

export const BackIcon = () => (
  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" aria-hidden>
    <path d="M20 12H5M11 5l-7 7 7 7" stroke="#082F57" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
)
export const HeartIcon = () => (
  <svg width="24" height="24" viewBox="0 0 24 24" aria-hidden>
    <path fill="#082F57" d="M12 21s-7.6-4.6-9.6-9.3C1 8.3 3.2 4.5 6.9 4.5c2 0 3.6 1.1 5.1 2.9 1.5-1.8 3.1-2.9 5.1-2.9 3.7 0 5.9 3.8 4.5 7.2C19.6 16.4 12 21 12 21z" />
  </svg>
)
export const BellIcon = () => (
  <svg width="24" height="24" viewBox="0 0 24 24" aria-hidden>
    <path fill="#082F57" d="M12 2.5a1.5 1.5 0 0 1 1.5 1.5v.7a6.5 6.5 0 0 1 5 6.3v4.2l1.7 2.3a.8.8 0 0 1-.6 1.3H4.4a.8.8 0 0 1-.6-1.3l1.7-2.3V11a6.5 6.5 0 0 1 5-6.3V4A1.5 1.5 0 0 1 12 2.5zM9.5 20h5a2.5 2.5 0 0 1-5 0z" />
  </svg>
)
export const ShareIcon = () => (
  <svg width="24" height="24" viewBox="0 0 24 24" aria-hidden>
    <g fill="#082F57"><circle cx="18" cy="5" r="3.2" /><circle cx="6" cy="12" r="3.2" /><circle cx="18" cy="19" r="3.2" /></g>
    <path d="M7.5 11l9-5M7.5 13l9 5" stroke="#082F57" strokeWidth="2.2" />
  </svg>
)

/** 16 px change arrow on a tinted circle. Down = Figma "Decrease"; up = the same shape turned, in green. */
export function ChangeIcon({ up, size = 16 }: { up: boolean; size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" aria-hidden className="shrink-0">
      <circle cx="8" cy="8" r="8" fill={up ? '#E6FAF4' : '#FCE8E9'} />
      <g transform={up ? 'rotate(180 8 8)' : undefined}>
        <path fillRule="evenodd" clipRule="evenodd" fill={up ? '#06CB90' : '#E11C23'}
          d="M5.23086 6.16963C4.85795 6.17435 4.55182 6.48048 4.5471 6.85339L4.49472 10.9913C4.49 11.3642 4.78848 11.6627 5.16139 11.6579L9.29927 11.6056C9.67219 11.6008 9.97832 11.2947 9.98304 10.9218C9.98776 10.5489 9.68928 10.2504 9.31637 10.2551L6.8086 10.2869L10.9598 6.13572C11.2268 5.8687 11.2322 5.44117 10.9718 5.18082C10.7115 4.92047 10.284 4.92589 10.0169 5.19291L5.86579 9.34407L5.89753 6.83629C5.90225 6.46338 5.60377 6.16491 5.23086 6.16963Z" />
      </g>
    </svg>
  )
}

/* ---------- Bottom sheet (opened by every ⓘ) ---------- */
export type SheetContent = { title: string; what?: string; how?: string; good_bad?: string; extra?: ReactNode }
const SheetCtx = createContext<(c: SheetContent | string) => void>(() => {})
export const useSheet = () => useContext(SheetCtx)

export function SheetProvider({ children }: { children: ReactNode }) {
  const { lang } = useSettings()
  const [c, setC] = useState<SheetContent | null>(null)
  const [shown, setShown] = useState(false)
  const open = (x: SheetContent | string) => {
    if (typeof x === 'string') {
      const g = glossary(lang, x)
      setC({ title: g?.label ?? x, what: g?.what, how: g?.how, good_bad: g?.good_bad })
    } else setC(x)
    requestAnimationFrame(() => setShown(true))
  }
  const close = () => { setShown(false); setTimeout(() => setC(null), 220) }
  useEffect(() => {
    const k = (e: KeyboardEvent) => e.key === 'Escape' && close()
    addEventListener('keydown', k); return () => removeEventListener('keydown', k)
  }, [])
  const ui = glossaryUi(lang)
  return (
    <SheetCtx.Provider value={open}>
      {children}
      {c && (
        <div className="fixed inset-0 z-40" role="dialog" aria-modal="true" aria-label={c.title}>
          <div onClick={close} className="absolute inset-0 bg-[#082f57]/40 transition-opacity duration-200" style={{ opacity: shown ? 1 : 0 }} />
          <div className="absolute left-0 right-0 bottom-0 bg-white rounded-t-3xl px-6 pt-3 pb-8 max-h-[80%] overflow-y-auto transition-transform duration-200 ease-out"
            style={{ transform: shown ? 'none' : 'translateY(100%)' }}>
            <div className="mx-auto mb-4 h-1 w-10 rounded-full bg-grey2" />
            <h3 className="t-subtitle text-navy m-0">{c.title}</h3>
            {c.extra && <div className="mt-3">{c.extra}</div>}
            {([['what', c.what], ['how', c.how], ['good_bad', c.good_bad]] as const).map(([k, v]) => v && (
              <div key={k} className="mt-4">
                <div className="t-label text-dgrey">{ui[k]}</div>
                <p className="t-body text-navy mt-1 mb-0 whitespace-pre-line">{v}</p>
              </div>
            ))}
            <button type="button" onClick={close} className="mt-6 w-full h-12 rounded-full bg-ink text-white t-link border-0 cursor-pointer">OK</button>
          </div>
        </div>
      )}
    </SheetCtx.Provider>
  )
}

/** Grey "i" circle. 16 px next to the price, 24 px in card titles. Opens the bottom sheet. */
export function InfoIcon({ size = 24, topic }: { size?: 16 | 24; topic?: string | SheetContent }) {
  const open = useSheet()
  const glyph = size === 24 ? 20 : 14
  const img = <img src={infoIcon} alt="" width={glyph} height={glyph} />
  if (!topic) return <span className="inline-grid place-items-center shrink-0" style={{ width: size, height: size }}>{img}</span>
  return (
    <button type="button" aria-label="What does this mean?" onClick={(e) => { e.stopPropagation(); open(topic) }}
      className="inline-grid place-items-center shrink-0 bg-transparent border-0 p-0 cursor-pointer relative after:absolute after:-inset-2.5"
      style={{ width: size, height: size }}>
      {img}
    </button>
  )
}

/* ---------- Layout pieces ---------- */

export const Divider = () => <div className="h-2 bg-lgrey w-full" />

/** The Figma card: white, 16 px corners, soft shadow, title row with a collapse chevron. */
export function Card({ title, info, extra, children, defaultOpen = true, flush = false }: {
  title: ReactNode; info?: string | SheetContent; extra?: ReactNode; children: ReactNode; defaultOpen?: boolean
  /** flush = content runs to the card edges (used by the forecast chart) */
  flush?: boolean
}) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <section className="bg-white rounded-2xl shadow-card overflow-hidden">
      <div className="flex items-center gap-4 p-4 pb-0">
        <div className="flex flex-1 items-center gap-2 min-w-0">
          <h2 className="t-link text-navy m-0">{title}</h2>
          {info && <InfoIcon topic={info} />}
          {extra}
        </div>
        <button
          type="button" onClick={() => setOpen(!open)} aria-expanded={open}
          aria-label={open ? 'Collapse' : 'Expand'}
          className="size-7 rounded-full bg-lavender grid place-items-center shrink-0 cursor-pointer border-0 p-0 relative after:absolute after:-inset-2"
        >
          <img src={chevronUp} alt="" width={24} height={24}
            className="transition-transform duration-200" style={{ transform: open ? 'none' : 'rotate(180deg)' }} />
        </button>
      </div>
      {open ? <div className={flush ? 'pt-4' : 'pt-4 px-4 pb-4'}>{children}</div> : <div className="h-4" />}
    </section>
  )
}

/** "2 Detail list" row: label left (Medium), value right (Bold), 26 px high. */
export function Row({ label, value, icon, sub }: { label: ReactNode; value: ReactNode; icon?: ReactNode; sub?: ReactNode }) {
  return (
    <div>
      <div className="flex items-center justify-between gap-3 min-h-[26px]">
        <div className="flex items-center gap-2 shrink-0 max-w-[58%]">
          {icon}
          <span className="t-body text-navy">{label}</span>
        </div>
        <div className="flex items-center justify-end gap-1 t-link text-navy text-right whitespace-nowrap min-w-0">{value}</div>
      </div>
      {sub && <div className="t-action text-dgrey mt-0.5">{sub}</div>}
    </div>
  )
}

/** Small bottom toast, e.g. "Prototype only" for the Buy / Sell buttons. */
export function Toast({ text }: { text: string | null }) {
  if (!text) return null
  return (
    <div role="status" className="fixed left-1/2 -translate-x-1/2 bottom-10 z-50 bg-ink text-white t-label px-5 py-3 rounded-full shadow-card pointer-events-none text-center max-w-[320px]">
      {text}
    </div>
  )
}

/* ---------- Pills: selected = purple fill (like the Figma "Rp" chip), others outlined ---------- */
export function Pills<T extends string>({ options, value, onChange, small = false, label }: {
  options: { key: T; label: string }[]; value: T; onChange: (k: T) => void; small?: boolean; label?: string
}) {
  return (
    <div role="tablist" aria-label={label} className="flex gap-2">
      {options.map((o) => {
        const on = o.key === value
        return (
          <button key={o.key} type="button" role="tab" aria-selected={on} onClick={() => onChange(o.key)}
            className={`rounded-full whitespace-nowrap cursor-pointer border ${small ? 'px-3 py-1 t-action-b' : 'px-4 h-9 t-label'} ${on ? 'bg-purple border-purple text-white' : 'bg-white border-grey2 text-dgrey'}`}>
            {o.label}
          </button>
        )
      })}
    </div>
  )
}

/* ---------- Tone chip: "Low debt" (green), "Pricier than usual" (red), neutral grey ---------- */
const TONE: Record<Tone, string> = {
  good: 'bg-up-bg text-[#048a62]', neutral: 'bg-grey2 text-dgrey', watch: 'bg-down-bg text-down', na: 'bg-lgrey text-grey',
}
export const ToneChip = ({ tone, children }: { tone: Tone; children: ReactNode }) => (
  <span className={`inline-block rounded-full px-2 py-0.5 t-action-b whitespace-nowrap ${TONE[tone]}`}>{children}</span>
)

/* ---------- Data badges (hidden unless switched on in the debug menu) ---------- */
const BADGE: Record<string, [string, string]> = {
  COMMERCIAL_OK: ['#06CB90', 'Licensed'], CALCULATED_SAFE: ['#3B82F6', 'Calculated'], DEMO_ONLY: ['#F59E0B', 'Demo data'],
}
export function Badge({ tag }: { tag?: string | null }) {
  const { badges } = useSettings()
  if (!badges || !tag || !BADGE[tag]) return null
  const [c, l] = BADGE[tag]
  return (
    <span className="inline-flex items-center gap-1 rounded-full px-1.5 text-[10px] leading-4 font-bold whitespace-nowrap align-middle"
      style={{ color: c, background: `${c}1f` }} title={l}>
      <span className="size-1.5 rounded-full" style={{ background: c }} />{l}
    </span>
  )
}

/** "N/A · reason" in grey. */
export const NA = ({ reason }: { reason?: string | null }) => {
  const r = (reason ?? '').replace(/^N\/A\s*\(?(.*?)\)?$/, '$1').trim()
  return <span className="t-label-m text-grey whitespace-normal text-right">N/A{r && r !== 'Not available' ? ` · ${r}` : ''}</span>
}

/** Show an API value with its formatter, or the N/A reason; plus the badge when badges are on. */
export function Val({ v, f }: { v?: V | null; f: (x: any) => ReactNode }) {
  if (!v || v.value == null) return <NA reason={v?.na_reason} />
  return <span className="inline-flex items-center gap-1">{f(v.value)}<Badge tag={v.license_tag} /></span>
}

/* ---------- Loading / error states ---------- */
export const Skeleton = ({ h = 120, className = '' }: { h?: number; className?: string }) => (
  <div className={`rounded-2xl bg-grey2 animate-pulse ${className}`} style={{ height: h }} aria-label="Loading" />
)

export function ErrorLine({ onRetry, detail }: { onRetry: () => void; detail?: string }) {
  const t = useT()
  return (
    <button type="button" onClick={onRetry} className="w-full text-left bg-transparent border-0 p-0 cursor-pointer">
      <span className="t-label-m text-down block">{t('retry')}</span>
      {detail && <span className="t-action text-grey block mt-1">{detail}</span>}
    </button>
  )
}

/** Card whose content depends on one API section: skeleton while loading, error line on failure. */
export function DataCard<T>({ q, title, info, children, defaultOpen, flush, h = 140 }: {
  q: Q<T>; title: ReactNode; info?: string | SheetContent; children: (d: T) => ReactNode; defaultOpen?: boolean; flush?: boolean; h?: number
}) {
  if (q.loading) return (
    <section className="bg-white rounded-2xl shadow-card p-4">
      <div className="t-link text-navy">{title}</div>
      <Skeleton h={h} className="mt-4" />
    </section>
  )
  return (
    <Card title={title} info={info} defaultOpen={defaultOpen} flush={flush && !q.error}>
      {q.error || q.data == null ? <ErrorLine onRetry={q.retry} detail={q.error} /> : children(q.data)}
    </Card>
  )
}

export const Empty = ({ children }: { children: ReactNode }) => (
  <p className="t-body text-dgrey m-0">{children}</p>
)
