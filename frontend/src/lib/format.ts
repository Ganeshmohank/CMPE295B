export function fmtPct(n: number | null | undefined) {
  if (n == null) return '—'
  return `${(n * 100).toFixed(1)}%`
}

export function fmtMs(n: number | null | undefined) {
  if (n == null) return '—'
  if (n >= 1000) return `${(n / 1000).toFixed(1)}s`
  return `${Math.round(n)} ms`
}

export function fmtNum(n: number | null | undefined, digits = 1) {
  if (n == null) return '—'
  return n.toFixed(digits)
}

export function fmtChars(n: number | null | undefined) {
  if (n == null) return '—'
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`
  return String(n)
}

export function relativeTime(iso: string) {
  const d = new Date(iso)
  const diff = Date.now() - d.getTime()
  const mins = Math.round(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.round(mins / 60)
  if (hrs < 48) return `${hrs}h ago`
  const days = Math.round(hrs / 24)
  return `${days}d ago`
}
