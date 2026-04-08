import './BreakdownBars.css'

type Props = {
  title: string
  data: Record<string, number>
  /** Optional fixed order of keys */
  order?: string[]
  variant?: 'default' | 'compact'
}

export function BreakdownBars({ title, data, order, variant = 'default' }: Props) {
  const d = data ?? {}
  const keys =
    order?.filter((k) => d[k] != null && d[k]! > 0) ?? Object.keys(d)
  const total = keys.reduce((s, k) => s + (d[k] ?? 0), 0)
  if (total === 0) return null

  return (
    <div className={`breakdown breakdown--${variant}`}>
      <div className="breakdown__title">{title}</div>
      <div className="breakdown__stack">
        {keys.map((k) => {
          const v = d[k] ?? 0
          const pct = (v / total) * 100
          return (
            <div key={k} className="breakdown__row">
              <div className="breakdown__label">
                <span className="breakdown__key">{k.replace(/_/g, ' ')}</span>
                <span className="breakdown__val">
                  {v}{' '}
                  <span className="breakdown__pct">({fmtPct(v / total)})</span>
                </span>
              </div>
              <div className="breakdown__track">
                <div className="breakdown__fill" style={{ width: `${pct}%` }} />
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function fmtPct(n: number) {
  return `${(n * 100).toFixed(0)}%`
}
