// Deadline date math (ADR-012 §14). Pure functions: "today" is always passed in, never read
// from the clock here, so this is deterministic and testable. The browser's LOCAL date is what
// the list filters and badges use (unlike posted/first-seen timestamps, which are UTC days).

/** The browser's local calendar date as YYYY-MM-DD (not UTC: a deadline is a local concept). */
export function localToday(): string {
  const now = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`
}

/** Whole days from `today` to `deadline` (both YYYY-MM-DD date-only strings). Negative once the
 * deadline has passed. Both are parsed as UTC midnight so a month/year boundary or DST shift in
 * the local zone never perturbs the day count. */
export function daysUntil(deadline: string, today: string): number {
  const ms = Date.parse(`${deadline}T00:00:00Z`) - Date.parse(`${today}T00:00:00Z`)
  return Math.round(ms / 86_400_000)
}

/** A known deadline 0-7 days away. Never true for a null deadline (ADR-012 §14). */
export function isClosingSoon(deadline: string | null, today: string): boolean {
  if (!deadline) return false
  const days = daysUntil(deadline, today)
  return days >= 0 && days <= 7
}

/** A known deadline strictly before today. Never true for a null deadline. */
export function isDeadlinePassed(deadline: string | null, today: string): boolean {
  return deadline !== null && daysUntil(deadline, today) < 0
}
