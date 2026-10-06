// ADR-025: display helpers for dashboard numbers. The API sends null when there is too little
// data to say anything; that must read as "not enough data", never 0%, NaN, or Infinity.

export const NO_DATA = 'Not enough data yet'

/** A 0-1 ratio as a whole percent, or the no-data text for null / non-finite values. */
export function formatRate(rate: number | null): string {
  return rate === null || !Number.isFinite(rate) ? NO_DATA : `${Math.round(rate * 100)}%`
}

/** Median days with one decimal, or the no-data text. */
export function formatDays(days: number | null): string {
  return days === null || !Number.isFinite(days) ? NO_DATA : `${days.toFixed(1)} days`
}

/** A percentage the API already rounded (0-100), or an em dash when there are no opportunities. */
export function formatPercent(percent: number | null): string {
  return percent === null || !Number.isFinite(percent) ? '—' : `${percent}%`
}

/** Widths for the pipeline bar: each status's share of all applications, never NaN. */
export function shares(counts: number[]): number[] {
  const total = counts.reduce((a, b) => a + b, 0)
  return counts.map((n) => (total > 0 ? (n / total) * 100 : 0))
}

export function greeting(hour: number): string {
  if (hour < 5) return 'Hello'
  if (hour < 12) return 'Good morning'
  if (hour < 18) return 'Good afternoon'
  return 'Good evening'
}

/** "3 hours ago" style age of an ISO instant, relative to `now`. */
export function ageText(iso: string | null, now: Date): string | null {
  if (!iso) return null
  const hours = (now.getTime() - new Date(iso).getTime()) / 3_600_000
  if (!Number.isFinite(hours) || hours < 0) return null
  if (hours < 1) return 'less than an hour ago'
  if (hours < 48) return `${Math.round(hours)} hours ago`
  return `${Math.floor(hours / 24)} days ago`
}

/** Bar heights (0-100) for the weekly trend, scaled to the largest week; all zeros, never NaN. */
export function barHeights(counts: number[]): number[] {
  const max = Math.max(0, ...counts.filter(Number.isFinite))
  return counts.map((n) => (max > 0 && Number.isFinite(n) ? (n / max) * 100 : 0))
}

/** Text equivalent of the trend chart. */
export function trendSummary(weeks: { week_start: string; count: number }[]): string {
  return weeks.length === 0
    ? 'No weekly data'
    : `New opportunities per week, oldest first: ${weeks.map((w) => `${w.week_start}: ${w.count}`).join('; ')}`
}
