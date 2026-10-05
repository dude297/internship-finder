import { useState, type FormEvent } from 'react'
import { api, ApiError, type FieldIssue } from '../api/client'
import type { Region, Source, SourceScope } from '../api/schemas'
import { describedBy, issueFor } from '../lib/forms'
import { buttonClass, fieldsetClass, inputClass, legendClass } from '../lib/styles'
import { ErrorMessage, Field } from './ui'

type Provider = 'greenhouse' | 'lever' | 'ashby' | 'smartrecruiters'

const boardHints: Record<Provider, string> = {
  greenhouse: 'For example https://job-boards.greenhouse.io/exampleboard',
  lever: 'For example https://jobs.lever.co/examplesite',
  ashby: 'For example https://jobs.ashbyhq.com/exampleboard, or just the board name',
  smartrecruiters:
    'For example https://jobs.smartrecruiters.com/ExampleCompany, or just the company identifier',
}

export const SCOPE_HINT =
  'Internships only keeps postings whose title says intern, internship, co-op, or apprentice. All postings imports full-time jobs too.'

/** Adds a Greenhouse board or Lever job site. The backend extracts the provider's board name
 * from the link and never requests the link itself. No API key is needed or accepted. */
export function AddSourceForm({ onAdded }: { onAdded: (source: Source) => void }) {
  const [provider, setProvider] = useState<Provider>('greenhouse')
  const [name, setName] = useState('')
  const [board, setBoard] = useState('')
  const [region, setRegion] = useState<Region>('global')
  const [scope, setScope] = useState<SourceScope>('internships_only')
  const [issues, setIssues] = useState<FieldIssue[]>([])
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault()
    setSaving(true)
    setError(null)
    setIssues([])
    try {
      const source = await api.createSource({
        kind: provider,
        display_name: name.trim(),
        board: board.trim(),
        region: provider === 'lever' && !board.includes('lever.co') ? region : null,
        scope,
      })
      setName('')
      setBoard('')
      onAdded(source)
    } catch (caught) {
      if (caught instanceof ApiError) {
        setIssues(caught.issues)
        setError(caught.issues.length ? null : caught.message)
      } else setError('Could not add the source.')
    } finally {
      setSaving(false)
    }
  }

  const boardError = issueFor(issues, 'board')
  const nameError = issueFor(issues, 'display_name')
  return (
    <form onSubmit={submit} noValidate>
      <fieldset className={fieldsetClass}>
        <legend className={legendClass}>Add a company job board</legend>
        {error && <ErrorMessage>{error}</ErrorMessage>}
        <Field id="source-provider" label="Provider">
          <select
            id="source-provider"
            value={provider}
            onChange={(e) => setProvider(e.target.value as Provider)}
            className={inputClass}
          >
            <option value="greenhouse">Greenhouse</option>
            <option value="lever">Lever</option>
            <option value="ashby">Ashby</option>
            <option value="smartrecruiters">SmartRecruiters</option>
          </select>
        </Field>
        <Field id="source-name" label="Organization name" error={nameError}>
          <input
            id="source-name"
            value={name}
            maxLength={200}
            required
            onChange={(e) => setName(e.target.value)}
            {...describedBy('source-name', undefined, nameError)}
            className={inputClass}
          />
        </Field>
        <Field
          id="source-board"
          label="Job board link or name"
          hint={boardHints[provider]}
          error={boardError}
        >
          <input
            id="source-board"
            value={board}
            maxLength={500}
            required
            onChange={(e) => setBoard(e.target.value)}
            {...describedBy('source-board', boardHints[provider], boardError)}
            className={inputClass}
          />
        </Field>
        {provider === 'lever' && (
          <Field
            id="source-region"
            label="Lever region"
            hint="Only used when you enter a site name; a jobs.eu.lever.co link means EU."
          >
            <select
              id="source-region"
              value={region}
              onChange={(e) => setRegion(e.target.value as Region)}
              aria-describedby="source-region-hint"
              className={inputClass}
            >
              <option value="global">Global (jobs.lever.co)</option>
              <option value="eu">EU (jobs.eu.lever.co)</option>
            </select>
          </Field>
        )}
        <Field id="source-scope" label="Import" hint={SCOPE_HINT}>
          <select
            id="source-scope"
            value={scope}
            onChange={(e) => setScope(e.target.value as SourceScope)}
            aria-describedby="source-scope-hint"
            className={inputClass}
          >
            <option value="internships_only">Internships only</option>
            <option value="all">All postings</option>
          </select>
        </Field>
        <button
          type="submit"
          className={buttonClass}
          disabled={saving || !name.trim() || !board.trim()}
        >
          {saving ? 'Adding…' : 'Add source'}
        </button>
      </fieldset>
    </form>
  )
}
