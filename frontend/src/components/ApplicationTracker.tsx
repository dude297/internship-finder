import { useState, type FormEvent } from 'react'
import { api } from '../api/client'
import {
  applicationStatuses,
  type Application,
  type ApplicationStatus,
} from '../api/schemas'
import { orNull } from '../lib/forms'
import { applicationStatusLabels } from '../lib/labels'
import { buttonClass, dangerButtonClass, inputClass } from '../lib/styles'
import { ErrorMessage, Field, SuccessMessage } from './ui'

/** Private application tracking. Changing it never changes eligibility. */
export function ApplicationTracker({
  opportunityId,
  application,
  onChange,
}: {
  opportunityId: string
  application: Application | null
  onChange: (application: Application | null) => void
}) {
  const [status, setStatus] = useState<ApplicationStatus>(application?.status ?? 'saved')
  const [submittedOn, setSubmittedOn] = useState(application?.submitted_on ?? '')
  const [notes, setNotes] = useState(application?.notes ?? '')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)

  async function run(action: () => Promise<Application | null>, done: string) {
    setBusy(true)
    setError(null)
    setMessage(null)
    try {
      onChange(await action())
      setMessage(done)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not save.')
    } finally {
      setBusy(false)
    }
  }

  const save = (event: FormEvent) => {
    event.preventDefault()
    void run(
      () =>
        api.saveApplication(opportunityId, {
          status,
          submitted_on: orNull(submittedOn),
          notes: orNull(notes),
        }),
      'Application tracking saved.',
    )
  }

  return (
    <section
      aria-labelledby="application-heading"
      className="space-y-3 rounded border p-4"
    >
      <h2 id="application-heading" className="text-lg font-semibold">
        Application
      </h2>
      {!application ? (
        <>
          <p className="text-slate-600">You're not tracking this opportunity yet.</p>
          <button
            type="button"
            disabled={busy}
            className={buttonClass}
            onClick={() =>
              void run(
                () =>
                  api.saveApplication(opportunityId, {
                    status: 'saved',
                    submitted_on: null,
                    notes: null,
                  }),
                'Now tracking this opportunity.',
              )
            }
          >
            Track this opportunity
          </button>
        </>
      ) : (
        <form onSubmit={save} className="space-y-3">
          <Field id="application-status" label="Status">
            <select
              id="application-status"
              value={status}
              onChange={(e) => setStatus(e.target.value as ApplicationStatus)}
              className={inputClass}
            >
              {applicationStatuses.map((s) => (
                <option key={s} value={s}>
                  {applicationStatusLabels[s]}
                </option>
              ))}
            </select>
          </Field>
          <Field id="application-submitted" label="Submitted on">
            <input
              id="application-submitted"
              type="date"
              value={submittedOn}
              onChange={(e) => setSubmittedOn(e.target.value)}
              className={inputClass}
            />
          </Field>
          <Field id="application-notes" label="Private notes">
            <textarea
              id="application-notes"
              rows={3}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              className={inputClass}
            />
          </Field>
          <div className="flex gap-3">
            <button type="submit" disabled={busy} className={buttonClass}>
              {busy ? 'Saving…' : 'Save application'}
            </button>
            <button
              type="button"
              disabled={busy}
              className={dangerButtonClass}
              onClick={() =>
                void run(async () => {
                  await api.deleteApplication(opportunityId)
                  setStatus('saved')
                  setSubmittedOn('')
                  setNotes('')
                  return null
                }, 'Stopped tracking this opportunity.')
              }
            >
              Stop tracking
            </button>
          </div>
        </form>
      )}
      {error && <ErrorMessage>{error}</ErrorMessage>}
      {message && <SuccessMessage>{message}</SuccessMessage>}
    </section>
  )
}
