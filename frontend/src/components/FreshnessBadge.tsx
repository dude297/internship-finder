import { useState } from 'react'
import type { FreshnessState, OpportunityDetail } from '../api/schemas'
import { isNewlyFound, relativeAge } from '../lib/freshness'
import { formatDate, formatDateTime, formatDay } from '../lib/labels'

// Freshness (M8.1): derived by the backend from source evidence. Text labels, never color
// alone. Wording says what was checked, never that a posting is guaranteed open.

// Tests inject `now`; otherwise the clock is read once per mount.
function useNow(now?: number): number {
  return useState(() => now ?? Date.now())[0]
}

interface FreshnessFields {
  freshness: FreshnessState
  freshness_checked_at: string | null
  program_last_verified: string | null
  verify_by: string | null
}

const styles: Record<FreshnessState, string> = {
  direct_verified: 'bg-green-100 text-green-800',
  program_listed: 'bg-sky-100 text-sky-900',
  program_recheck: 'border border-amber-400 bg-amber-100 text-amber-900',
  feed_current: 'bg-slate-100 text-slate-700',
  source_warning: 'border border-amber-400 bg-amber-100 text-amber-900',
  manual: 'bg-slate-100 text-slate-700',
  closed: '',
}

function ageSuffix(o: FreshnessFields, now: number): string {
  return o.freshness_checked_at ? ` · ${relativeAge(o.freshness_checked_at, now)}` : ''
}

function freshnessLabel(o: FreshnessFields, now: number): string | null {
  switch (o.freshness) {
    case 'direct_verified':
      return `Confirmed on company board${ageSuffix(o, now)}`
    case 'program_listed': {
      const parts = [
        o.program_last_verified &&
          `Program checked ${formatDate(o.program_last_verified)}`,
        o.verify_by && `re-check ${formatDate(o.verify_by)}`,
      ].filter(Boolean)
      return parts.length ? parts.join(' · ') : 'Program listed'
    }
    case 'program_recheck':
      return 'Program info needs re-check'
    case 'feed_current':
      return `Seen in community feed only${ageSuffix(o, now)}`
    case 'source_warning':
      return 'Company board check pending'
    case 'manual':
      return 'Added manually'
    case 'closed':
      return null
  }
}

function freshnessExplanation(o: FreshnessFields, now: number): string | null {
  const age = o.freshness_checked_at ? relativeAge(o.freshness_checked_at, now) : null
  switch (o.freshness) {
    case 'direct_verified':
      return (
        "Confirmed on the company's own job board in its latest complete sync" +
        (age ? `, ${age}.` : '.')
      )
    case 'program_listed':
      return 'Hand-verified program information from official pages. Dates are only as current as the last check.'
    case 'program_recheck':
      return `The program's information was due for re-checking${
        o.verify_by ? ` on ${formatDate(o.verify_by)}` : ''
      }.`
    case 'feed_current':
      return "Listed in the community discovery feed in its latest sync. The company's own posting wasn't checked directly."
    case 'source_warning':
      return 'Company board check pending: the latest sync of its source(s) was partial, failed, or is out of date, so a closed posting may still appear open.'
    case 'manual':
      return 'You manage this opportunity by hand.'
    case 'closed':
      return null
  }
}

/** One small badge. In the list (`compact`), manual and closed postings show nothing extra. */
export function FreshnessBadge({
  o,
  compact = false,
  now: nowProp,
}: {
  o: FreshnessFields
  compact?: boolean
  now?: number
}) {
  const now = useNow(nowProp)
  if (compact && o.freshness === 'manual') return null
  const label = freshnessLabel(o, now)
  if (!label) return null
  return (
    <span
      className={`rounded px-1.5 py-0.5 ${styles[o.freshness]}`}
      title={freshnessExplanation(o, now) ?? undefined}
    >
      {label}
    </span>
  )
}

/** "New" = first found by Internship Finder in the last 7 days; not the company's posted date. */
export function NewBadge({
  firstSeenAt,
  postedAt,
  now: nowProp,
}: {
  firstSeenAt: string
  postedAt: string | null
  now?: number
}) {
  const now = useNow(nowProp)
  if (!isNewlyFound(firstSeenAt, now)) return null
  const title =
    `First found by Internship Finder on ${formatDay(firstSeenAt)}` +
    (postedAt ? `. Posted by the company ${formatDay(postedAt)}` : '')
  return (
    <span className="rounded bg-violet-100 px-1.5 py-0.5 text-violet-900" title={title}>
      New
    </span>
  )
}

/** Detail-page verdict (the one authoritative place; per-source sync lives on the Source cards). */
export function FreshnessSection({
  opportunity,
  now: nowProp,
}: {
  opportunity: OpportunityDetail
  now?: number
}) {
  const now = useNow(nowProp)
  const o = opportunity
  const explanation =
    freshnessExplanation(o, now) ??
    'No source lists this posting anymore, so there is no freshness to report.'
  return (
    <section aria-labelledby="freshness-heading" className="space-y-2">
      <h2 id="freshness-heading" className="text-lg font-semibold">
        Freshness
      </h2>
      <p>{explanation}</p>
      {o.freshness_checked_at && (
        <p className="text-sm text-slate-600">
          Last confirmed {formatDateTime(o.freshness_checked_at)}
        </p>
      )}
    </section>
  )
}
