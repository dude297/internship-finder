import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { api } from '../api/client'
import type { OpportunityDetail } from '../api/schemas'
import { ApplicationTracker } from '../components/ApplicationTracker'
import { EligibilityPanel } from '../components/EligibilityPanel'
import { ErrorMessage } from '../components/ui'
import {
  appliesAtLabels,
  assessmentLabels,
  formatDate,
  opportunityTypeLabels,
  remoteModeLabels,
  requirementTypeLabels,
} from '../lib/labels'
import { dangerButtonClass, secondaryButtonClass } from '../lib/styles'

function describeValue(value: Record<string, unknown>): string {
  if (typeof value.years === 'number') return `at least ${value.years} years old`
  if (Array.isArray(value.levels)) {
    const levels = value.levels.join(' or ').replaceAll('_', ' ')
    return value.accepts_incoming ? `${levels} (incoming students accepted)` : levels
  }
  if (Array.isArray(value.countries)) return value.countries.join(', ')
  return typeof value.description === 'string' ? value.description : ''
}

export function OpportunityDetailPage() {
  const { id = '' } = useParams()
  const navigate = useNavigate()
  const [opportunity, setOpportunity] = useState<OpportunityDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    // Ignore responses that arrive after unmount or a re-run (e.g. StrictMode runs effects
    // twice), so a late response can't overwrite what the user already typed.
    let active = true
    api
      .getOpportunity(id)
      .then((o) => active && setOpportunity(o))
      .catch(
        (caught: unknown) =>
          active &&
          setError(caught instanceof Error ? caught.message : 'Could not load it.'),
      )
    return () => {
      active = false
    }
  }, [id])

  if (error) return <ErrorMessage>{error}</ErrorMessage>
  if (!opportunity) return <p role="status">Loading…</p>
  const o = opportunity

  async function reevaluate() {
    setBusy(true)
    try {
      await api.evaluateOpportunity(id)
      setOpportunity(await api.getOpportunity(id))
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not re-evaluate.')
    } finally {
      setBusy(false)
    }
  }

  async function remove() {
    if (
      !window.confirm(`Delete "${o.title}"? This also deletes its tracking and history.`)
    )
      return
    setBusy(true)
    try {
      await api.deleteOpportunity(id)
      navigate('/opportunities', { replace: true })
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not delete it.')
      setBusy(false)
    }
  }

  const facts: [string, string][] = [
    ['Type', opportunityTypeLabels[o.opportunity_type]],
    ['Location', o.location ?? '—'],
    ['Remote mode', o.remote_mode ? remoteModeLabels[o.remote_mode] : '—'],
    ['Application deadline', formatDate(o.application_deadline)],
    ['Start date', formatDate(o.start_date)],
    ['End date', formatDate(o.end_date)],
  ]

  return (
    <article className="space-y-6">
      <header className="space-y-1">
        <Link to="/opportunities" className="text-sm underline">
          ← All opportunities
        </Link>
        <h1 className="text-2xl font-semibold">{o.title}</h1>
        <p className="text-slate-600">{o.organization}</p>
        <div className="flex flex-wrap gap-2 pt-2">
          <Link to={`/opportunities/${o.id}/edit`} className={secondaryButtonClass}>
            Edit
          </Link>
          <button
            type="button"
            onClick={reevaluate}
            disabled={busy || !o.profile_exists}
            className={secondaryButtonClass}
          >
            Re-evaluate
          </button>
          <button
            type="button"
            onClick={remove}
            disabled={busy}
            className={dangerButtonClass}
          >
            Delete
          </button>
        </div>
      </header>

      <EligibilityPanel opportunity={o} />

      <section aria-labelledby="details-heading" className="space-y-2">
        <h2 id="details-heading" className="text-lg font-semibold">
          Details
        </h2>
        <dl className="grid grid-cols-1 gap-x-4 gap-y-1 sm:grid-cols-2">
          {facts.map(([label, value]) => (
            <div key={label}>
              <dt className="inline text-slate-500">{label}: </dt>
              <dd className="inline">{value}</dd>
            </div>
          ))}
        </dl>
        {o.application_url && (
          <p>
            <a
              href={o.application_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-blue-800 underline"
            >
              Application page
            </a>
          </p>
        )}
        {o.description && <p className="whitespace-pre-wrap">{o.description}</p>}
      </section>

      <section aria-labelledby="requirements-heading" className="space-y-2">
        <h2 id="requirements-heading" className="text-lg font-semibold">
          Requirements
        </h2>
        <p>
          <span className="text-slate-500">Assessment: </span>
          {assessmentLabels[o.requirements_assessment_status]}
        </p>
        {o.requirements.length === 0 ? (
          <p className="text-slate-600">No requirements recorded.</p>
        ) : (
          <ul className="list-disc space-y-1 pl-5">
            {o.requirements.map((r) => (
              <li key={r.id}>
                <span className="font-medium">
                  {requirementTypeLabels[r.requirement_type]}
                </span>
                : {describeValue(r.value)}
                {(r.requirement_type === 'minimum_age' ||
                  r.requirement_type === 'education') && (
                  <span className="text-slate-600">
                    {' '}
                    ({appliesAtLabels[r.applies_at].toLowerCase()}
                    {r.reference_date ? `: ${formatDate(r.reference_date)}` : ''})
                  </span>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      <ApplicationTracker
        opportunityId={o.id}
        application={o.application}
        onChange={(application) => setOpportunity({ ...o, application })}
      />
    </article>
  )
}
