// Small display helpers.

/** "2026-10-03" -> "Oct 3" (or "Oct 3, 2025" outside the current year). Parsed as a local date. */
export function formatDate(isoDate: string): string {
  const [y, m, d] = isoDate.slice(0, 10).split('-').map(Number)
  const date = new Date(y, m - 1, d)
  const sameYear = y === new Date().getFullYear()
  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric', ...(sameYear ? {} : { year: 'numeric' }) })
}

export function daysAgo(days: number): string {
  if (days <= 0) return 'today'
  if (days === 1) return 'yesterday'
  return `${days} days ago`
}

/** ISO timestamp -> "just now", "5 min ago", "3 h ago", "2 days ago". */
export function timeAgo(iso: string, now: Date = new Date()): string {
  const secs = Math.max(0, (now.getTime() - new Date(iso).getTime()) / 1000)
  if (secs < 60) return 'just now'
  const mins = Math.floor(secs / 60)
  if (mins < 60) return `${mins} min ago`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours} h ago`
  const days = Math.floor(hours / 24)
  return days === 1 ? 'yesterday' : `${days} days ago`
}

/** 180 -> "3h", 90 -> "90 min", 1440 -> "day". For "Auto-sync every …". */
export function interval(minutes: number): string {
  if (minutes % 1440 === 0) return minutes === 1440 ? 'day' : `${minutes / 1440} days`
  if (minutes % 60 === 0) return `${minutes / 60}h`
  return `${minutes} min`
}

export function percent(rate: number): string {
  return `${Math.round(rate * 100)}%`
}

/** Today as YYYY-MM-DD in local time (for <input type="date">). */
export function todayISO(): string {
  const d = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

/** ISO timestamp -> "Oct 3, 14:05" in local time. */
export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}
