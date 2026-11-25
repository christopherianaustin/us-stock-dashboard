// Small Recharts helpers in the Nanovest style: no grid clutter, short labels, max ~8-12 bars, tap for exact values.
import type { ReactNode } from 'react'
import { ResponsiveContainer, Tooltip } from 'recharts'

export const C = {
  navy: '#082F57', ink: '#111A28', purple: '#561FA3', purpleLight: '#B79CE8', green: '#06CB90', red: '#E11C23',
  grey: '#A3B1BE', grey2: '#E8EBEF', dgrey: '#7C8D9D', blue: '#52B1FE', amber: '#F5A524',
}

export const axisTick = { fill: C.dgrey, fontSize: 10, fontWeight: 500 }

/** Fixed-height chart box (Recharts needs a sized parent). */
export const ChartBox = ({ h = 180, children }: { h?: number; children: ReactNode }) => (
  <div style={{ width: '100%', height: h }}>
    <ResponsiveContainer width="100%" height="100%">{children as any}</ResponsiveContainer>
  </div>
)

/** Tap tooltip: white card with the exact values. */
export function TapTip({ fmt }: { fmt: (v: number, name: string) => string }) {
  return (
    <Tooltip
      cursor={{ fill: 'rgba(86,31,163,0.06)', stroke: C.grey2 }}
      wrapperStyle={{ outline: 'none', zIndex: 5 }}
      content={({ active, payload, label }) => !active || !payload?.length ? null : (
        <div className="bg-white rounded-lg shadow-card px-3 py-2 t-action text-navy">
          <div className="t-action-b mb-0.5">{String(label)}</div>
          {payload.map((p: any) => p.value != null && (
            <div key={p.dataKey} className="flex items-center gap-1.5 whitespace-nowrap">
              <span className="size-2 rounded-full" style={{ background: p.color ?? p.fill }} />
              {p.name}: <b>{fmt(Number(p.value), String(p.name))}</b>
            </div>
          ))}
        </div>
      )}
    />
  )
}

/** Simple legend row under a chart. */
export const Legend = ({ items }: { items: [string, string][] }) => (
  <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2">
    {items.map(([label, color]) => (
      <span key={label} className="flex items-center gap-1.5 t-action text-dgrey">
        <span className="size-2.5 rounded-sm" style={{ background: color }} />{label}
      </span>
    ))}
  </div>
)
