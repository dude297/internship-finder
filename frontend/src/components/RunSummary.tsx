import type { Run } from '../api/schemas'
import { formatDateTime, runStatusLabels } from '../lib/labels'

const statusStyles: Record<Run['status'], string> = {
  running: 'bg-slate-100 text-slate-800',
  success: 'bg-green-100 text-green-800',
  partial: 'bg-amber-100 text-amber-900',
  failed: 'bg-red-100 text-red-800',
  no_change: 'bg-slate-100 text-slate-800',
}

function seconds(run: Run): string | null {
  if (!run.finished_at) return null
  const ms = new Date(run.finished_at).getTime() - new Date(run.started_at).getTime()
  return `${(ms / 1000).toFixed(1)} s`
}

/** One ingestion run: status, counts, and a few safe error lines (never payloads). */
export function RunSummary({ run }: { run: Run }) {
  const counts: [string, number][] = [
    ['Fetched', run.fetched_count],
    ['Filtered', run.filtered_count],
    ['Created', run.created_count],
    ['Updated', run.updated_count],
    ['Merged with another source', run.deduplicated_count],
    ['Unchanged', run.unchanged_count],
    ['Closed', run.closed_count],
    ['Reopened', run.reactivated_count],
    ['Invalid', run.invalid_count],
    ['Errors', run.error_count],
  ]
  const duration = seconds(run)
  return (
    <div className="space-y-2 text-sm">
      <p className="flex flex-wrap items-center gap-2">
        <span className={`rounded px-2 py-0.5 font-medium ${statusStyles[run.status]}`}>
          {runStatusLabels[run.status]}
        </span>
        <span className="text-slate-600">
          {formatDateTime(run.started_at)}
          {duration && ` · ${duration}`}
        </span>
      </p>
      {run.error_summary && <p className="text-red-800">{run.error_summary}</p>}
      {run.status !== 'failed' && run.status !== 'no_change' && (
        <dl className="grid grid-cols-2 gap-x-4 gap-y-0.5 sm:grid-cols-3">
          {counts.map(([label, value]) => (
            <div key={label}>
              <dt className="inline text-slate-500">{label}: </dt>
              <dd className="inline">{value}</dd>
            </div>
          ))}
        </dl>
      )}
      {run.status === 'no_change' && (
        <p className="text-slate-600">The source hasn't changed since the last sync.</p>
      )}
      {run.status === 'partial' && (
        <p className="text-slate-600">
          Some items couldn't be imported, so postings missing from this sync weren't
          marked closed.
        </p>
      )}
      {run.errors.length > 0 && run.status !== 'failed' && (
        <details>
          <summary className="cursor-pointer">Problems ({run.errors.length})</summary>
          <ul className="mt-1 list-disc pl-5 text-slate-700">
            {run.errors.slice(0, 20).map((e, index) => (
              <li key={index}>
                {e.external_id && <span className="font-mono">{e.external_id}: </span>}
                {e.message}
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  )
}
