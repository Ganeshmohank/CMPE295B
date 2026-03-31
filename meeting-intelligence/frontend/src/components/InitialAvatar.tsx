import './InitialAvatar.css'

export function InitialAvatar({ name }: { name: string | null | undefined }) {
  const initials = (name ?? '?')
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase() ?? '')
    .join('') || '?'

  const hue =
    ((name ?? '').split('').reduce((a, c) => a + c.charCodeAt(0), 0) % 360) || 210

  return (
    <span
      className="initial-avatar"
      style={{ background: `linear-gradient(135deg, hsl(${hue}, 45%, 38%), hsl(${(hue + 40) % 360}, 50%, 32%))` }}
      aria-hidden
    >
      {initials}
    </span>
  )
}
