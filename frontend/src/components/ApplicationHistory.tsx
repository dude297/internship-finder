import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { ApplicationEvent } from '../api/schemas'
import { eventLabel } from '../lib/applications'
import { applicationStatusLabels } from '../lib/labels'

const local = (iso: unknown) =>
  typeof iso === 'string' && !Number.isNaN(Date.parse(iso))
    ? new Date(iso).toLocaleString()
    : null

function detail(event: ApplicationEvent): string | null {
  const m = event.metadata_json
  switch (event.event_type) {
    case 'next_action_changed':
      return m.length === 0 ? 'cleared' : null
    case 'deadline_changed':
      return typeof m.to === 'string' ? `due ${m.to}` : 'cleared'
    case 'interview_scheduled':
    case 'interview_updated':
      return local(m.to) ?? 'cleared'
    default:
      return null
  }
}

/** ADR-025: changes recorded since this feature shipped, oldest first. Older applications simply
 * start with whatever is recorded from now on. `refreshKey` reloads after the owner saves. */
export function ApplicationHistory({
  applicationId,
  refreshKey,
}: {
  applicationId: string
  refreshKey: string
}) {
  const [events, setEvents] = useState<ApplicationEvent[] | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    let active = true
    api
      .getApplicationEvents(applicationId)
      .then((r) => active && (setEvents(r.items), setFailed(false)))
      .catch(() => active && setFailed(true))
    return () => {
      active = false
    }
  }, [applicationId, refreshKey])

  return (
    <section aria-labelledby="history-heading" className="space-y-2">
      <h3 id="history-heading" className="font-semibold">
        History
      </h3>
      {failed ? (
        <p className="text-sm text-slate-600">Couldn't load the history.</p>
      ) : events === null ? (
        <p className="text-sm text-slate-600">Loading…</p>
      ) : events.length === 0 ? (
        <p className="text-sm text-slate-600">
          No recorded history yet. Changes are recorded from now on.
        </p>
      ) : (
        <ol className="divide-y divide-slate-200 text-sm">
          {events.map((e) => {
            const extra = detail(e)
            return (
              <li key={e.id} className="flex flex-wrap gap-x-3 py-1.5">
                <time dateTime={e.occurred_at} className="w-44 shrink-0 text-slate-600">
                  {new Date(e.occurred_at).toLocaleString()}
                </time>
                <span>
                  {eventLabel(
                    e.event_type,
                    e.from_status,
                    e.to_status,
                    applicationStatusLabels,
                  )}
                  {extra && <span className="text-slate-600"> · {extra}</span>}
                </span>
              </li>
            )
          })}
        </ol>
      )}
    </section>
  )
}
