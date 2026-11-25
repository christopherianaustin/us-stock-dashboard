import { useState } from 'react'
import { API_BASE, MOCK_TICKERS, QUICK_TICKERS } from '../config'
import { useSettings, type Mode } from '../lib/data'
import { Pills } from './ui'

/** Hidden menu (tap the ticker 5 times): stock picker, language, data mode, safe mode, data badges. */
export function DebugMenu({ onClose, src }: { onClose: () => void; src?: string }) {
  const s = useSettings()
  const [tk, setTk] = useState(s.ticker)
  const go = (t: string) => { s.setTicker(t); onClose() }
  const Switch = ({ on, set, label, help }: { on: boolean; set: (b: boolean) => void; label: string; help: string }) => (
    <button type="button" role="switch" aria-checked={on} onClick={() => set(!on)} className="w-full flex items-center gap-3 bg-transparent border-0 p-0 text-left cursor-pointer">
      <span className="flex-1"><span className="t-label text-navy block">{label}</span><span className="t-action text-dgrey block">{help}</span></span>
      <span className={`w-11 h-6 rounded-full p-0.5 transition-colors ${on ? 'bg-purple' : 'bg-grey2'}`}>
        <span className={`block size-5 rounded-full bg-white shadow transition-transform ${on ? 'translate-x-5' : ''}`} />
      </span>
    </button>
  )
  return (
    <div className="fixed inset-0 z-40" role="dialog" aria-modal="true" aria-label="Debug menu">
      <div className="absolute inset-0 bg-[#082f57]/40" onClick={onClose} />
      <div className="absolute left-0 right-0 bottom-0 bg-white rounded-t-3xl px-6 pt-3 pb-8 max-h-[85%] overflow-y-auto">
        <div className="mx-auto mb-4 h-1 w-10 rounded-full bg-grey2" />
        <h3 className="t-subtitle text-navy m-0">Prototype settings</h3>

        <div className="t-label text-navy mt-5">Stock</div>
        <form className="flex gap-2 mt-2" onSubmit={(e) => { e.preventDefault(); go(tk) }}>
          <input value={tk} onChange={(e) => setTk(e.target.value.toUpperCase())} aria-label="Ticker"
            className="flex-1 h-10 rounded-full border border-grey2 px-4 t-label text-navy outline-none focus:border-purple" placeholder="e.g. MSFT" />
          <button type="submit" className="h-10 px-5 rounded-full bg-ink text-white t-label border-0 cursor-pointer">Open</button>
        </form>
        <div className="flex flex-wrap gap-2 mt-2">
          {QUICK_TICKERS.map((t) => (
            <button key={t} type="button" onClick={() => go(t)}
              className={`rounded-full px-3 py-1 t-action-b border cursor-pointer ${t === s.ticker ? 'bg-purple border-purple text-white' : 'bg-white border-grey2 text-navy'}`}>{t}</button>
          ))}
        </div>
        <p className="t-action text-dgrey mt-1 mb-0">Saved data (works offline): {MOCK_TICKERS.join(', ')}. Other stocks need the API running.</p>

        <div className="t-label text-navy mt-5">Language</div>
        <div className="mt-2"><Pills small value={s.lang} onChange={s.setLang} options={[{ key: 'en', label: 'English' }, { key: 'id', label: 'Bahasa Indonesia' }]} /></div>

        <div className="t-label text-navy mt-5">Data mode</div>
        <div className="mt-2">
          <Pills<Mode> small value={s.mode} onChange={s.setMode}
            options={[{ key: 'auto', label: 'Auto' }, { key: 'live', label: 'Live API' }, { key: 'mock', label: 'Saved data' }]} />
        </div>
        <p className="t-action text-dgrey mt-1 mb-0">
          Auto = live API at {API_BASE}, saved data if it can't be reached. Now showing: <b>{src === 'live' ? 'live API' : src === 'mock' ? 'saved data' : '…'}</b>
        </p>

        <div className="flex flex-col gap-4 mt-5">
          <Switch on={s.safe} set={s.setSafe} label="Production-safe mode" help="Hide every value that is not licensed for commercial use." />
          <Switch on={s.badges} set={s.setBadges} label="Data badges" help="Show where each number comes from (green licensed, blue calculated, orange demo)." />
        </div>

        <button type="button" onClick={onClose} className="mt-6 w-full h-12 rounded-full bg-ink text-white t-link border-0 cursor-pointer">Done</button>
      </div>
    </div>
  )
}
