/**
 * Display formatting. The API deals in integer euro cents (D3, D26) and
 * aware-UTC ISO-8601 strings (D33); this is the one place they become
 * human-readable values. Never do float math here — only display rounding.
 */

const eur = new Intl.NumberFormat('en-IE', { style: 'currency', currency: 'EUR' })

/** Integer cents → "€14.50" (non-enumerable-safe, display only). */
export function money(cents) {
  const n = Math.trunc(Number(cents) || 0)
  const sign = n < 0 ? '-' : ''
  return `${sign}${eur.format(Math.abs(n) / 100)}`
}

/** ISO-8601 string (e.g. 2026-11-07T18:03:12+00:00) → local medium date/time. */
export function formatDateTime(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  return new Intl.DateTimeFormat('en-GB', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(d)
}

/** "12 minutes" / "3 hours" style relative age, for reminders. */
export function timeAgo(iso) {
  if (!iso) return ''
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return ''
  const minutes = Math.max(0, Math.round((Date.now() - then) / 60000))
  if (minutes < 1) return 'just now'
  if (minutes < 60) return `${minutes} min ago`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours} h ago`
  return `${Math.round(hours / 24)} d ago`
}
