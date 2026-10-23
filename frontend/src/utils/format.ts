/** Whole metres for display; the API returns 2 decimals. */
export function formatMetres(distance: number): string {
  return `${Math.round(distance).toLocaleString('en-MY')} m`
}

/** One decimal under 10 minutes so card values and their difference add up (API assumes 1.2 m/s). */
export function formatMinutes(minutes: number): string {
  return `${minutes < 10 ? minutes.toFixed(1) : Math.round(minutes)} min`
}

export function formatSigned(value: number, unit: string, decimals = 0): string {
  const rounded = Number(value.toFixed(decimals))
  if (rounded === 0) return `±0 ${unit}`
  const magnitude = Math.abs(rounded).toLocaleString('en-MY', { minimumFractionDigits: decimals, maximumFractionDigits: decimals })
  return `${rounded > 0 ? '+' : '−'}${magnitude} ${unit}`
}

/** Relative time for report timestamps. Falls back to the raw string if it can't be parsed. */
export function formatRelative(iso: string, now = Date.now()): string {
  // The backend emits microseconds (…:00.123456Z); trim to milliseconds for reliable parsing.
  const parsed = Date.parse(iso.replace(/(\.\d{3})\d+/, '$1'))
  if (Number.isNaN(parsed)) return iso
  const seconds = Math.round((now - parsed) / 1000)
  if (seconds < 45) return 'just now'
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `${minutes} min ago`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours} h ago`
  return new Date(parsed).toLocaleDateString('en-MY', { day: 'numeric', month: 'short' })
}
