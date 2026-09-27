import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { api } from '../api/client'
import type { OpportunitySummary } from '../api/schemas'
import { EligibilityBadge } from '../components/EligibilityBadge'
import { ErrorMessage } from '../components/ui'
import {
  applicationStatusLabels,
  assessmentLabels,
  formatDate,
  opportunityTypeLabels,
  remoteModeLabels,
} from '../lib/labels'
import { buttonClass } from '../lib/styles'

function where(o: OpportunitySummary): string {
  const parts = [o.location, o.remote_mode && remoteModeLabels[o.remote_mode]].filter(
    Boolean,
  )
  return parts.length ? parts.join(' · ') : 'Location not set'
}

export function OpportunityListPage() {
  const [items, setItems] = useState<OpportunitySummary[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    // Ignore responses that arrive after unmount or a re-run (e.g. StrictMode runs effects
    // twice), so a late response can't overwrite what the user already typed.
    let active = true
    api
      .listOpportunities()
      .then((items) => active && setItems(items))
      .catch(
        (caught: unknown) =>
          active &&
          setError(
            caught instanceof Error ? caught.message : 'Could not load opportunities.',
          ),
      )
    return () => {
      active = false
    }
  }, [])

  return (
    <section className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Opportunities</h1>
        <Link to="/opportunities/new" className={buttonClass}>
          Add opportunity
        </Link>
      </div>
      {error && <ErrorMessage>{error}</ErrorMessage>}
      {!error && !items && <p role="status">Loading opportunities…</p>}
      {items?.length === 0 && (
        <p className="rounded border border-dashed border-slate-300 p-6 text-center text-slate-600">
          No opportunities yet. Add one to check your eligibility.
        </p>
      )}
      {items && items.length > 0 && (
        <ul className="space-y-3">
          {items.map((o) => (
            <li key={o.id} className="rounded border border-slate-200 p-4">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div>
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
                </div>
                <EligibilityBadge status={o.eligibility_status} />
              </div>
              <dl className="mt-2 grid grid-cols-1 gap-x-4 gap-y-1 text-sm sm:grid-cols-2">
                <div>
                  <dt className="inline text-slate-500">Deadline: </dt>
                  <dd className="inline">{formatDate(o.application_deadline)}</dd>
                </div>
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
      )}
    </section>
  )
}
