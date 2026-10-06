import { useState } from 'react'
import { api } from '../api/client'
import type { ApplicationStatus } from '../api/schemas'
import {
  actionLabels,
  availableActions,
  patchFor,
  type QuickAction,
} from '../lib/applications'
import { secondaryButtonClass } from '../lib/styles'

/** ADR-025: one-click status changes plus the two actions that need a date. */
export function ApplicationQuickActions({
  opportunityId,
  status,
  applicationUrl,
  onSaved,
}: {
  opportunityId: string
  status: ApplicationStatus
  applicationUrl?: string | null
  onSaved: () => void
}) {
  const [open, setOpen] = useState<'follow_up' | 'interview' | null>(null)
  const [date, setDate] = useState('')
  const [text, setText] = useState('')
  const [at, setAt] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function run(action: QuickAction) {
    setBusy(true)
    setError(null)
    try {
      await api.saveApplication(
        opportunityId,
        patchFor(action, status, {
          followUpDate: date,
          followUpText: text,
          interviewAt: at,
        }),
      )
      setOpen(null)
      setDate('')
      setText('')
      setAt('')
      onSaved()
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not save.')
    } finally {
      setBusy(false)
    }
  }

  function click(action: QuickAction) {
    if (action === 'follow_up' || action === 'interview')
      setOpen(open === action ? null : action)
    else void run(action)
  }

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-2 text-sm">
        {availableActions(status).map((action) => (
          <button
            key={action}
            type="button"
            disabled={busy}
            aria-expanded={action === open ? true : undefined}
            className={secondaryButtonClass}
            onClick={() => click(action)}
          >
            {actionLabels[action]}
          </button>
        ))}
        {applicationUrl && (
          <a
            href={applicationUrl}
            target="_blank"
            rel="noopener noreferrer"
            className={`${secondaryButtonClass} inline-block`}
          >
            Open application link
          </a>
        )}
      </div>
      {open === 'follow_up' && (
        <form
          className="flex flex-wrap items-end gap-2 text-sm"
          onSubmit={(e) => {
            e.preventDefault()
            void run('follow_up')
          }}
        >
          <label>
            Follow-up date
            <input
              type="date"
              required
              value={date}
              onChange={(e) => setDate(e.target.value)}
              className="ml-1 rounded border border-slate-300 px-2 py-1"
            />
          </label>
          <label>
            What
            <input
              type="text"
              maxLength={200}
              placeholder="Follow up"
              value={text}
              onChange={(e) => setText(e.target.value)}
              className="ml-1 rounded border border-slate-300 px-2 py-1"
            />
          </label>
          <button type="submit" disabled={busy} className={secondaryButtonClass}>
            Save follow-up
          </button>
        </form>
      )}
      {open === 'interview' && (
        <form
          className="flex flex-wrap items-end gap-2 text-sm"
          onSubmit={(e) => {
            e.preventDefault()
            void run('interview')
          }}
        >
          <label>
            Interview date and time (your local time)
            <input
              type="datetime-local"
              required
              value={at}
              onChange={(e) => setAt(e.target.value)}
              className="ml-1 rounded border border-slate-300 px-2 py-1"
            />
          </label>
          <button type="submit" disabled={busy} className={secondaryButtonClass}>
            Save interview
          </button>
        </form>
      )}
      {error && (
        <p role="alert" className="text-sm text-red-800">
          {error}
        </p>
      )}
    </div>
  )
}
