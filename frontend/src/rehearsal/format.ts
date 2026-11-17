// Display helpers shared by the session-record views (Sessions, and the private-host
// Dashboard, Agents and Costs). Missing values stay "Unavailable", never zero.
export const text = (value: unknown, max = 1000) => typeof value === 'string' ? value.length > max ? `${value.slice(0, max)}… [truncated]` : value : ''
export const label = (value: string) => text(value, 100).replaceAll('_', ' ').replace(/^./, character => character.toUpperCase())
export function dollars(value: string | null | undefined) {
  if (value === null || value === undefined) return 'Unavailable'
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return 'Unavailable'
  if (numeric === 0 && !/[1-9]/.test(value)) return '$0'
  if (Math.abs(numeric) < 1e-12) return '<$0.000000000001'
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 12 }).format(numeric)
}
export const elapsed = (value: number | null | undefined) => value === null || value === undefined ? 'Unavailable' : `${value} ms`
