// Freshness helpers (M8.1). Pure: "now" is always passed in so tests are deterministic.
// Wording never promises a posting is open; it only says what was last checked and where.

const HOUR = 3_600_000
const DAY = 24 * HOUR

/** "just now", "5m ago", "3h ago", "2d ago" from an ISO timestamp. */
export function relativeAge(iso: string, now: number): string {
  const ms = now - Date.parse(iso)
  if (!(ms >= 60_000)) return 'just now'
  if (ms < HOUR) return `${Math.floor(ms / 60_000)}m ago`
  if (ms < DAY) return `${Math.floor(ms / HOUR)}h ago`
  return `${Math.floor(ms / DAY)}d ago`
}

/** First found by Internship Finder within the last 7 days (not the provider's posted date). */
export function isNewlyFound(firstSeenAt: string, now: number): boolean {
  return now - Date.parse(firstSeenAt) < 7 * DAY
}
