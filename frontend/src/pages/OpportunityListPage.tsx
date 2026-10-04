import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router'
import { api } from '../api/client'
import type { OpportunityPage, OpportunitySummary, Source } from '../api/schemas'
import { EligibilityBadge } from '../components/EligibilityBadge'
import { FitBadge } from '../components/FitBadge'
import { OpportunityFilters, type FilterName } from '../components/OpportunityFilters'
import { ErrorMessage } from '../components/ui'
import { isClosingSoon, isDeadlinePassed, localToday } from '../lib/deadlines'
import {
  applicationStatusLabels,
  assessmentLabels,
  formatDay,
  opportunityTypeLabels,
  remoteModeLabels,
} from '../lib/labels'
import { buttonClass, secondaryButtonClass } from '../lib/styles'

const PAGE_SIZE = 50
const FILTERS: FilterName[] = [
  'q',
  'availability',
  'source',
  'eligibility',
  'application_status',
  'remote_mode',
  'opportunity_type',
  'sort',
  'requirements_assessment_status',
  'requirement_review',
  'deadline_within',
]

function where(o: OpportunitySummary): string {
  const parts = [o.location, o.remote_mode && remoteModeLabels[o.remote_mode]].filter(
    Boolean,
  )
  return parts.length ? parts.join(' · ') : 'Location not set'
}

function Provenance({ o }: { o: OpportunitySummary }) {
  return (
    <p className="flex flex-wrap items-center gap-2 text-xs text-slate-600">
      <span className="rounded bg-slate-100 px-1.5 py-0.5">
        {o.origin === 'imported' ? 'Imported' : 'Manual'}
      </span>
      {o.availability === 'closed' && (
        <span className="rounded bg-slate-700 px-1.5 py-0.5 text-white">Closed</span>
      )}
      {o.origin === 'imported' && <span>{o.source_names.join(', ')}</span>}
      <span>
        {o.posted_at
          ? `Posted ${formatDay(o.posted_at)}`
          : `Found ${formatDay(o.first_seen_at)}`}
      </span>
    </p>
  )
}

/** Deadline and requirement-review badges (ADR-012 §8, §14): text labels, never color alone. */
function ReviewBadges({ o, today }: { o: OpportunitySummary; today: string }) {
  const deadline = o.application_deadline
  return (
    <p className="flex flex-wrap gap-1 text-xs">
      {isDeadlinePassed(deadline, today) && (
        <span className="rounded bg-slate-700 px-1.5 py-0.5 text-white">
          Deadline passed
        </span>
      )}
      {isClosingSoon(deadline, today) && (
        <span className="rounded bg-amber-100 px-1.5 py-0.5 text-amber-900">
          Closing soon
        </span>
      )}
      {o.pending_requirement_count > 0 && (
        <span className="rounded bg-sky-100 px-1.5 py-0.5 text-sky-900">
          {o.pending_requirement_count} suggestion
          {o.pending_requirement_count === 1 ? '' : 's'}
        </span>
      )}
      {o.requirements_stale && (
        <span className="rounded bg-amber-100 px-1.5 py-0.5 text-amber-900">
          Review needed
        </span>
      )}
    </p>
  )
}

export function OpportunityListPage() {
  const [params, setParams] = useSearchParams()
  // The latest response and the query it answers: an error only shows for the current query,
  // and the previous page stays visible while the next one loads.
  const [result, setResult] = useState<{
    query: string
    page: OpportunityPage | null
    error: string | null
  } | null>(null)
  const [sources, setSources] = useState<Source[]>([])

  const values = Object.fromEntries(
    FILTERS.map((name) => [name, params.get(name) ?? '']),
  ) as Record<FilterName, string>
  values.availability ||= 'open'
  // Eligibility first, then fit; without evaluations this is the same as newest.
  values.sort ||= 'recommended'
  const offset = Math.max(0, Number(params.get('offset')) || 0)
  const query = JSON.stringify({ ...values, offset })
  const page = result?.page ?? null
  const error = result?.query === query ? result.error : null

  useEffect(() => {
    let active = true
    api
      .listSources()
      .then((s) => active && setSources(s))
      .catch(() => {}) // the source filter just stays short; the list reports real errors
    return () => {
      active = false
    }
  }, [])

  useEffect(() => {
    // Ignore responses that arrive after unmount or a newer query, so a slow response can't
    // overwrite the page the user is now looking at.
    let active = true
    const { availability, sort, deadline_within, ...rest } = JSON.parse(
      query,
    ) as typeof values & {
      offset: number
    }
    // The single "Deadline" select carries either a day count or "has a deadline"; both need
    // the browser's local date so the backend's day math matches what the badges show.
    const deadlineParams =
      deadline_within === 'has_deadline'
        ? { has_deadline: 'true' as const, today: localToday() }
        : deadline_within
          ? { deadline_within: deadline_within as '7' | '14' | '30', today: localToday() }
          : sort === 'deadline'
            ? { today: localToday() }
            : {}
    api
      .listOpportunities({
        ...rest,
        ...deadlineParams,
        availability: availability as 'open' | 'closed' | 'all',
        sort: sort as 'recommended' | 'newest' | 'deadline',
        requirement_review: (rest.requirement_review || undefined) as
          'pending' | 'stale' | 'needs_review' | undefined,
        limit: PAGE_SIZE,
      })
      .then((p) => active && setResult({ query, page: p, error: null }))
      .catch(
        (caught: unknown) =>
          active &&
          setResult({
            query,
            page: null,
            error:
              caught instanceof Error ? caught.message : 'Could not load opportunities.',
          }),
      )
    return () => {
      active = false
    }
  }, [query])

  function update(changes: Record<string, string>) {
    const next = new URLSearchParams(params)
    for (const [name, value] of Object.entries(changes)) {
      if (value) next.set(name, value)
      else next.delete(name)
    }
    setParams(next)
  }

  const filtered = FILTERS.some(
    (name) => name !== 'availability' && name !== 'sort' && values[name],
  )
  const items = page?.items
  const today = localToday()

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-2xl font-semibold">Opportunities</h1>
        <Link to="/opportunities/new" className={buttonClass}>
          Add opportunity
        </Link>
      </div>
      <OpportunityFilters
        values={values}
        sources={sources}
        onChange={(name, value) => update({ [name]: value, offset: '' })}
      />
      {error && <ErrorMessage>{error}</ErrorMessage>}
      {!error && !page && <p role="status">Loading opportunities…</p>}
      {items?.length === 0 && (
        <p className="rounded border border-dashed border-slate-300 p-6 text-center text-slate-600">
          {filtered || values.availability !== 'open'
            ? 'No opportunities match these filters.'
            : 'No opportunities yet. Sync a source or add one by hand.'}
        </p>
      )}
      {page && items && items.length > 0 && (
        <>
          <p className="text-sm text-slate-600" role="status">
            Showing {page.offset + 1}–{page.offset + items.length} of {page.total}
          </p>
          <ul className="space-y-3">
            {items.map((o) => (
              <li key={o.id} className="rounded border border-slate-200 p-4">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="space-y-1">
                    <h2 className="font-medium">
                      <Link
                        to={`/opportunities/${o.id}`}
                        className="text-blue-800 underline"
                      >
                        {o.title}
                      </Link>
                    </h2>
                    <p className="text-sm text-slate-600">
                      {o.organization} · {opportunityTypeLabels[o.opportunity_type]}
                    </p>
                    <Provenance o={o} />
                    <ReviewBadges o={o} today={today} />
                  </div>
                  <div className="flex flex-col items-end gap-1">
                    <FitBadge score={o.fit_score} coverage={o.fit_coverage} />
                    <EligibilityBadge status={o.eligibility_status} />
                  </div>
                </div>
                <dl className="mt-2 grid grid-cols-1 gap-x-4 gap-y-1 text-sm sm:grid-cols-2">
                  <div>
                    <dt className="inline text-slate-500">Where: </dt>
                    <dd className="inline">{where(o)}</dd>
                  </div>
                  <div>
                    <dt className="inline text-slate-500">Requirements: </dt>
                    <dd className="inline">
                      {assessmentLabels[o.requirements_assessment_status]}
                    </dd>
                  </div>
                  <div>
                    <dt className="inline text-slate-500">Application: </dt>
                    <dd className="inline">
                      {o.application_status
                        ? applicationStatusLabels[o.application_status]
                        : 'Not tracked'}
                    </dd>
                  </div>
                </dl>
              </li>
            ))}
          </ul>
          <nav aria-label="Pages" className="flex items-center justify-between">
            <button
              type="button"
              className={secondaryButtonClass}
              disabled={page.offset === 0}
              onClick={() =>
                update({ offset: String(Math.max(0, page.offset - PAGE_SIZE) || '') })
              }
            >
              Previous
            </button>
            <button
              type="button"
              className={secondaryButtonClass}
              disabled={page.offset + items.length >= page.total}
              onClick={() => update({ offset: String(page.offset + PAGE_SIZE) })}
            >
              Next
            </button>
          </nav>
        </>
      )}
    </section>
  )
}
