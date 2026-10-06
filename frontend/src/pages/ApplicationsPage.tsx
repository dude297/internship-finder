import { useCallback, useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router'
import { api } from '../api/client'
import {
  applicationSorts,
  applicationStatuses,
  type ApplicationListItem,
  type ApplicationSort,
  type ApplicationStatus,
} from '../api/schemas'
import { ApplicationQuickActions } from '../components/ApplicationQuickActions'
import { ErrorMessage } from '../components/ui'
import { pipelineColumns } from '../lib/applications'
import { localToday } from '../lib/deadlines'
import { applicationStatusLabels } from '../lib/labels'
import { inputClass } from '../lib/styles'

const sortLabels: Record<ApplicationSort, string> = {
  next_action: 'Next action',
  newest: 'Newest',
  applied: 'Applied date',
  interview: 'Interview date',
  company: 'Company',
  stage: 'Stage',
}

function ApplicationCard({
  item,
  onChanged,
}: {
  item: ApplicationListItem
  onChanged: () => void
}) {
  const [error, setError] = useState<string | null>(null)

  async function changeStage(status: ApplicationStatus) {
    setError(null)
    try {
      await api.saveApplication(item.opportunity_id, { status })
      onChanged()
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not save.')
    }
  }

  return (
    <li className="space-y-2 py-3">
      <div className="flex flex-wrap items-baseline gap-x-2">
        <Link
          to={`/opportunities/${item.opportunity_id}`}
          className="font-medium text-blue-800 underline"
        >
          {item.title}
        </Link>
        <span className="text-slate-600">· {item.organization}</span>
      </div>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-slate-700">
        <label className="flex items-center gap-1">
          <span className="text-slate-600">Stage</span>
          <select
            aria-label={`Stage for ${item.title}`}
            value={item.status}
            onChange={(e) => void changeStage(e.target.value as ApplicationStatus)}
            className="rounded border border-slate-300 px-1 py-0.5"
          >
            {applicationStatuses.map((s) => (
              <option key={s} value={s}>
                {applicationStatusLabels[s]}
              </option>
            ))}
          </select>
        </label>
        {item.next_action_due && (
          <span
            className={item.follow_up_overdue ? 'font-medium text-red-800' : undefined}
          >
            {item.next_action ?? 'Follow up'} · due {item.next_action_due}
            {item.follow_up_overdue && ' (overdue)'}
          </span>
        )}
        {item.interview_at && (
          <span>Interview {new Date(item.interview_at).toLocaleString()}</span>
        )}
        {item.applied_at && (
          <span>Applied {new Date(item.applied_at).toLocaleDateString()}</span>
        )}
      </div>
      <ApplicationQuickActions
        opportunityId={item.opportunity_id}
        status={item.status}
        applicationUrl={item.application_url}
        onSaved={onChanged}
      />
      {error && (
        <p role="alert" className="text-sm text-red-800">
          {error}
        </p>
      )}
    </li>
  )
}

function Cards({
  items,
  onChanged,
}: {
  items: ApplicationListItem[]
  onChanged: () => void
}) {
  return (
    <ul className="divide-y divide-slate-200">
      {items.map((item) => (
        <ApplicationCard key={item.id} item={item} onChanged={onChanged} />
      ))}
    </ul>
  )
}

/** ADR-025: the application workspace. The Dashboard is the overview and the Inbox the action
 * queue; this is where you work on applications. Stages are for scanning, not a fixed order. */
export function ApplicationsPage() {
  const [params] = useSearchParams()
  const initialStage = applicationStatuses.find((s) => s === params.get('stage')) ?? ''
  const [view, setView] = useState<'list' | 'pipeline'>('list')
  const [stage, setStage] = useState<ApplicationStatus | ''>(initialStage)
  const [company, setCompany] = useState('')
  const [sort, setSort] = useState<ApplicationSort>('next_action')
  const [overdue, setOverdue] = useState(false)
  const [dueSoon, setDueSoon] = useState(false)
  const [interviews, setInterviews] = useState(false)
  const [mobileColumn, setMobileColumn] = useState(pipelineColumns[0].key)
  const [items, setItems] = useState<ApplicationListItem[] | null>(null)
  const [total, setTotal] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [reload, setReload] = useState(0)

  const changed = useCallback(() => setReload((n) => n + 1), [])

  useEffect(() => {
    let active = true
    api
      .listApplications({
        stage: view === 'list' && stage ? [stage] : undefined,
        company,
        sort,
        due_soon: dueSoon,
        follow_up_overdue: overdue,
        interview_upcoming: interviews,
        today: localToday(),
      })
      .then((page) => {
        if (!active) return
        setItems(page.items)
        setTotal(page.total)
        setError(null)
      })
      .catch((caught: unknown) => {
        if (active)
          setError(
            caught instanceof Error
              ? caught.message
              : 'Could not load your applications.',
          )
      })
    return () => {
      active = false
    }
  }, [view, stage, company, sort, dueSoon, overdue, interviews, reload])

  const tab = (v: 'list' | 'pipeline', label: string) => (
    <button
      type="button"
      role="tab"
      aria-selected={view === v}
      onClick={() => setView(v)}
      className={`rounded px-3 py-1 ${view === v ? 'bg-slate-900 text-white' : 'border border-slate-300 hover:bg-slate-100'}`}
    >
      {label}
    </button>
  )

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold">Applications</h1>
        <p className="text-sm text-slate-600">
          Your workspace for tracked applications. The{' '}
          <Link to="/dashboard" className="underline">
            Dashboard
          </Link>{' '}
          is the overview and the{' '}
          <Link to="/inbox" className="underline">
            Inbox
          </Link>{' '}
          is the action queue.
        </p>
      </div>

      <div role="tablist" aria-label="View" className="flex gap-2">
        {tab('list', 'List')}
        {tab('pipeline', 'Pipeline')}
      </div>

      <div className="flex flex-wrap items-end gap-3 text-sm">
        {view === 'list' && (
          <label>
            Stage
            <select
              value={stage}
              onChange={(e) => setStage(e.target.value as ApplicationStatus | '')}
              className={inputClass}
            >
              <option value="">All stages</option>
              {applicationStatuses.map((s) => (
                <option key={s} value={s}>
                  {applicationStatusLabels[s]}
                </option>
              ))}
            </select>
          </label>
        )}
        <label>
          Company
          <input
            type="search"
            value={company}
            onChange={(e) => setCompany(e.target.value)}
            className={inputClass}
          />
        </label>
        <label>
          Sort by
          <select
            value={sort}
            onChange={(e) => setSort(e.target.value as ApplicationSort)}
            className={inputClass}
          >
            {applicationSorts.map((s) => (
              <option key={s} value={s}>
                {sortLabels[s]}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-1">
          <input
            type="checkbox"
            checked={overdue}
            onChange={(e) => setOverdue(e.target.checked)}
          />
          Follow-up overdue
        </label>
        <label className="flex items-center gap-1">
          <input
            type="checkbox"
            checked={dueSoon}
            onChange={(e) => setDueSoon(e.target.checked)}
          />
          Due soon
        </label>
        <label className="flex items-center gap-1">
          <input
            type="checkbox"
            checked={interviews}
            onChange={(e) => setInterviews(e.target.checked)}
          />
          Interview upcoming
        </label>
      </div>

      {error && <ErrorMessage>{error}</ErrorMessage>}
      {!items && !error && (
        <p role="status" aria-live="polite">
          Loading…
        </p>
      )}
      {items && items.length === 0 && (
        <p className="text-slate-600">
          No applications match.{' '}
          <Link to="/opportunities" className="underline">
            Track an opportunity
          </Link>{' '}
          to start.
        </p>
      )}
      {items && items.length > 0 && view === 'list' && (
        <>
          <p className="text-sm text-slate-600">
            {total} application{total === 1 ? '' : 's'}
          </p>
          <Cards items={items} onChanged={changed} />
        </>
      )}
      {items && items.length > 0 && view === 'pipeline' && (
        <>
          <div
            role="tablist"
            aria-label="Stage"
            className="flex flex-wrap gap-1 md:hidden"
          >
            {pipelineColumns.map((c) => (
              <button
                key={c.key}
                type="button"
                role="tab"
                aria-selected={mobileColumn === c.key}
                onClick={() => setMobileColumn(c.key)}
                className={`rounded px-2 py-1 text-sm ${mobileColumn === c.key ? 'bg-slate-200 font-medium' : 'border border-slate-300'}`}
              >
                {c.label} ({items.filter((i) => c.statuses.includes(i.status)).length})
              </button>
            ))}
          </div>
          <div className="grid gap-4 md:grid-cols-3 lg:grid-cols-6">
            {pipelineColumns.map((c) => {
              const column = items.filter((i) => c.statuses.includes(i.status))
              return (
                <section
                  key={c.key}
                  aria-label={`${c.label} column`}
                  className={`min-w-0 ${mobileColumn === c.key ? '' : 'hidden'} md:block`}
                >
                  <h2 className="border-b border-slate-200 pb-1 font-semibold">
                    {c.label}{' '}
                    <span className="font-normal text-slate-600">({column.length})</span>
                  </h2>
                  {column.length === 0 ? (
                    <p className="py-2 text-sm text-slate-500">None</p>
                  ) : (
                    <Cards items={column} onChanged={changed} />
                  )}
                </section>
              )
            })}
          </div>
        </>
      )}
    </div>
  )
}
